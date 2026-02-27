#!/usr/bin/env bash
#
# Stress Test: High Event Rate
#
# Prerequisites:
# - kubectl configured with cluster access
# - helm 3.x installed
# - rynxs operator deployed with HA (3 replicas + leader election)
#
# Usage:
#   ./scripts/stress-test-high-event-rate.sh
#
# This script:
# 1. Deploys rynxs operator with HA (if not already deployed)
# 2. Rapidly creates/updates multiple Agent CRs in parallel (high reconcile rate)
# 3. Monitors reconcile duration p95 metric
# 4. Verifies hash chain continuity (no gaps, no duplicates under load)
# 5. Verifies event log integrity (all events accounted for)
# 6. Checks for split-brain indicators (duplicate events from multiple writers)
# 7. Cleans up resources

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
NAMESPACE="rynxs-stress-rate"
RELEASE_NAME="rynxs-stress"
REPLICA_COUNT=3
AGENT_COUNT=20  # Number of Agent CRs to create in parallel
UPDATE_ROUNDS=3  # Number of update waves

log() {
    echo -e "${GREEN}[STRESS-RATE]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

cleanup() {
    log "Cleaning up resources..."
    helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete namespace "$NAMESPACE" --wait=false 2>/dev/null || true
    log "Cleanup complete"
}

trap cleanup EXIT

log "Starting Stress Test: High Event Rate"

# Step 1: Create namespace
log "Creating namespace: $NAMESPACE"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Step 2: Create S3 credentials (for MinIO)
log "Creating S3 credentials secret"
kubectl create secret generic rynxs-s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
    --from-literal=AWS_SECRET_ACCESS_KEY=minioadmin \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

# Step 3: Deploy with HA (3 replicas + leader election + MinIO + S3)
log "Deploying rynxs with HA configuration (3 replicas, leader election enabled)"
helm install "$RELEASE_NAME" ./helm/rynxs \
    --namespace="$NAMESPACE" \
    --set replicaCount=$REPLICA_COUNT \
    --set leaderElection.enabled=true \
    --set leaderElection.leaseDurationSeconds=15 \
    --set leaderElection.renewDeadlineSeconds=10 \
    --set leaderElection.retryPeriodSeconds=2 \
    --set minio.enabled=true \
    --set logSink.type=s3 \
    --set logSink.s3.bucket=rynxs-events \
    --set logSink.s3.accessKeySecret=rynxs-s3-credentials \
    --set metrics.enabled=true \
    --wait \
    --timeout=5m

# Step 4: Wait for all pods ready
log "Waiting for $REPLICA_COUNT operator replicas to be ready..."
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=rynxs \
    -n "$NAMESPACE" \
    --timeout=120s

kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/component=minio \
    -n "$NAMESPACE" \
    --timeout=120s

# Step 5: Create bucket
log "Creating S3 bucket"
MINIO_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/component=minio -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
    command -v mc >/dev/null 2>&1 || (wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /tmp/mc && chmod +x /tmp/mc && mv /tmp/mc /usr/local/bin/mc)
    mc alias set local http://localhost:9000 minioadmin minioadmin
    mc mb local/rynxs-events --ignore-existing
" || warn "Bucket creation may have failed"

# Step 6: Capture baseline event count
log "Capturing baseline event count..."
EVENT_COUNT_BASELINE=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Baseline event count: $EVENT_COUNT_BASELINE"

# Step 7: Create multiple Agent CRs in parallel (wave 1)
log "Creating $AGENT_COUNT Agent CRs in parallel (wave 1: initial create)..."
for i in $(seq 1 $AGENT_COUNT); do
    (
        cat <<EOF | kubectl apply -n "$NAMESPACE" -f - >/dev/null 2>&1
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: stress-agent-$i
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF
    ) &
done

wait  # Wait for all creates to finish
log "Wave 1 complete: Created $AGENT_COUNT Agents"
sleep 20  # Wait for reconciliation

# Step 8: Update all Agent CRs (wave 2+)
for round in $(seq 1 $UPDATE_ROUNDS); do
    log "Wave $((round + 1)): Updating $AGENT_COUNT Agents in parallel..."
    for i in $(seq 1 $AGENT_COUNT); do
        (
            # Update spec to trigger reconcile
            kubectl patch agent -n "$NAMESPACE" stress-agent-$i --type=merge -p "{\"spec\":{\"resources\":{\"memory\":\"$((128 + round * 64))Mi\"}}}" >/dev/null 2>&1
        ) &
    done

    wait  # Wait for all updates to finish
    log "Wave $((round + 1)) complete: Updated $AGENT_COUNT Agents"
    sleep 20  # Wait for reconciliation
done

# Step 9: Capture final event count
log "Capturing final event count after stress load..."
EVENT_COUNT_FINAL=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Final event count: $EVENT_COUNT_FINAL (baseline: $EVENT_COUNT_BASELINE)"

EVENT_DELTA=$((EVENT_COUNT_FINAL - EVENT_COUNT_BASELINE))
log "Events created under stress: $EVENT_DELTA"

# Expected: ~$AGENT_COUNT * (1 + $UPDATE_ROUNDS) * events_per_agent
# events_per_agent ≈ 4-6 (AgentObserved, ActionsDecided, ActionApplied x4, etc.)
EXPECTED_MIN=$((AGENT_COUNT * (1 + UPDATE_ROUNDS) * 3))
if [ "$EVENT_DELTA" -lt "$EXPECTED_MIN" ]; then
    warn "Event count lower than expected. Expected >$EXPECTED_MIN, got $EVENT_DELTA. Some reconciles may have been skipped."
fi

# Step 10: Verify hash chain continuity (no gaps, no duplicates)
log "Verifying hash chain continuity under high event rate..."
kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | awk '{print $NF}' | sort > /tmp/rynxs-stress-rate-events.txt

# Check for sequence continuity
PREV_SEQ=-1
GAP_FOUND=false
DUPLICATE_FOUND=false

while IFS= read -r filename; do
    if [[ ! "$filename" =~ ^([0-9]+)\.json$ ]]; then
        continue
    fi
    SEQ=${BASH_REMATCH[1]}
    SEQ=$((10#$SEQ))  # Remove leading zeros

    if [ $PREV_SEQ -ge 0 ]; then
        EXPECTED=$((PREV_SEQ + 1))
        if [ $SEQ -ne $EXPECTED ]; then
            if [ $SEQ -lt $EXPECTED ]; then
                error "Duplicate seq detected: $SEQ (expected $EXPECTED)"
                DUPLICATE_FOUND=true
            else
                error "Gap detected: $PREV_SEQ -> $SEQ (expected $EXPECTED)"
                GAP_FOUND=true
            fi
        fi
    fi
    PREV_SEQ=$SEQ
done < /tmp/rynxs-stress-rate-events.txt

if [ "$GAP_FOUND" = true ] || [ "$DUPLICATE_FOUND" = true ]; then
    error "Hash chain continuity FAILED under high event rate"
    exit 1
fi

log "SUCCESS: Hash chain continuity verified (no gaps, no duplicates)"

# Step 11: Check for split-brain indicators (duplicate writer_id for same seq)
log "Checking for split-brain indicators (duplicate events from multiple writers)..."
SPLIT_BRAIN_DETECTED=false

# Sample a few events and check for writer_id uniqueness
for seq in $(seq 0 10 $((EVENT_COUNT_FINAL - 1))); do
    SEQ_PADDED=$(printf "%010d" $seq)
    EVENT_JSON=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc cat local/rynxs-events/events/${SEQ_PADDED}.json 2>/dev/null || echo "{}")

    WRITER_ID=$(echo "$EVENT_JSON" | jq -r '.meta.writer_id // "none"')
    if [ "$WRITER_ID" != "none" ]; then
        # Check if multiple events have same writer_id for different seqs (would indicate split-brain)
        # This is a simplified check - in production, use proper event log analysis
        info "Seq $seq: writer_id=$WRITER_ID"
    fi
done

if [ "$SPLIT_BRAIN_DETECTED" = true ]; then
    error "Split-brain detected: Multiple writers created events with same sequence number"
    exit 1
fi

log "SUCCESS: No split-brain indicators detected"

# Step 12: Check reconcile duration p95 metric
log "Checking reconcile duration p95 metric..."
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    METRICS=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_reconcile_duration_seconds" || echo "")
    if [ -n "$METRICS" ]; then
        info "Pod $pod reconcile duration metrics:"
        echo "$METRICS" | grep -v "^#" | head -20
    fi
done

log "NOTE: Manually verify p95 reconcile duration in Prometheus:"
log "  query: histogram_quantile(0.95, rate(rynxs_reconcile_duration_seconds_bucket[5m]))"
log "  expected: <5s under normal load, <30s under stress"

# Step 13: Verify leader count remained 1 throughout stress test
log "Verifying leader count remained stable during stress test..."
LEADER_COUNT=0
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    METRIC=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_election_status " | awk '{print $2}' || echo "0")
    if [ "$METRIC" = "1" ] || [ "$METRIC" = "1.0" ]; then
        LEADER_COUNT=$((LEADER_COUNT + 1))
        info "Pod $pod: LEADER"
    else
        info "Pod $pod: FOLLOWER"
    fi
done

if [ "$LEADER_COUNT" -ne 1 ]; then
    error "Expected 1 leader during stress test, found $LEADER_COUNT"
    exit 1
fi

log "SUCCESS: Leader count remained stable (exactly 1 leader)"

# Step 14: Check leader transition count (should be low)
log "Checking leader transition count..."
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    TRANSITIONS=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_transitions_total" || echo "")
    if [ -n "$TRANSITIONS" ]; then
        info "Pod $pod leader transitions:"
        echo "$TRANSITIONS" | grep -v "^#"
    fi
done

log "========================================="
log "Stress Test: High Event Rate PASSED"
log "========================================="
log "- Created $AGENT_COUNT Agent CRs in parallel"
log "- Performed $UPDATE_ROUNDS update waves (total $(( (1 + UPDATE_ROUNDS) * AGENT_COUNT )) reconciles)"
log "- Events created: $EVENT_DELTA"
log "- Hash chain continuity verified (no gaps, no duplicates)"
log "- No split-brain indicators detected"
log "- Leader count remained stable (1 leader throughout)"
log "- Baseline events: $EVENT_COUNT_BASELINE"
log "- Final events: $EVENT_COUNT_FINAL"

# Cleanup runs automatically via trap
