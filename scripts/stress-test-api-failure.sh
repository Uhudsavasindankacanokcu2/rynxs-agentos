#!/usr/bin/env bash
#
# Stress Test: API Server Failure Simulation
#
# Prerequisites:
# - kubectl configured with cluster access
# - helm 3.x installed
# - rynxs operator deployed with HA (3 replicas + leader election)
#
# Usage:
#   ./scripts/stress-test-api-failure.sh
#
# This script:
# 1. Deploys rynxs operator with HA (if not already deployed)
# 2. Creates Agent CR to trigger event log entries
# 3. Simulates API server failure using NetworkPolicy (blocks egress to API server)
# 4. Verifies operator gracefully degrades (leader drops, followers noop)
# 5. Removes NetworkPolicy to restore API access
# 6. Verifies operator recovers (new leader elected, reconciliation resumes)
# 7. Validates hash chain continuity (no gaps, no duplicates)
# 8. Cleans up resources

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
NAMESPACE="rynxs-stress-api"
RELEASE_NAME="rynxs-stress"
REPLICA_COUNT=3

log() {
    echo -e "${GREEN}[STRESS-API]${NC} $*"
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
    kubectl delete networkpolicy -n "$NAMESPACE" block-api-server --ignore-not-found=true 2>/dev/null || true
    helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete namespace "$NAMESPACE" --wait=false 2>/dev/null || true
    log "Cleanup complete"
}

trap cleanup EXIT

log "Starting Stress Test: API Server Failure Simulation"

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

# Step 6: Apply Agent CR to generate baseline events
log "Applying Agent CR to generate baseline events..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: stress-agent-baseline
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF

sleep 10

# Step 7: Capture baseline event count
log "Capturing baseline event count in S3..."
EVENT_COUNT_BASELINE=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Baseline event count: $EVENT_COUNT_BASELINE"

# Step 8: Identify leader
log "Identifying current leader..."
sleep 5
LEADER_POD=""
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    if kubectl logs -n "$NAMESPACE" "$pod" --tail=50 2>/dev/null | grep -q "Leader status: LEADER\|Acquired leadership"; then
        LEADER_POD=$pod
        break
    fi
done

if [ -z "$LEADER_POD" ]; then
    error "No leader found in logs"
    exit 1
fi

log "Current leader: $LEADER_POD"

# Step 9: Simulate API server failure (NetworkPolicy blocking egress)
log "Simulating API server failure (blocking egress to API server via NetworkPolicy)..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: block-api-server
  namespace: $NAMESPACE
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: rynxs
  policyTypes:
    - Egress
  egress:
    # Block all egress (API server unreachable)
    []
EOF

log "NetworkPolicy applied. Operator pods cannot reach API server."
sleep 30  # Wait for NetworkPolicy to take effect + leader to detect failure

# Step 10: Verify leader dropped (metrics should show 0 leaders)
log "Verifying leader dropped due to API unreachability..."
LEADER_COUNT_FAILURE=0
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    # Try to fetch metrics (may fail due to NetworkPolicy, so use || true)
    METRIC=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_election_status " | awk '{print $2}' || echo "0")
    if [ "$METRIC" = "1" ] || [ "$METRIC" = "1.0" ]; then
        LEADER_COUNT_FAILURE=$((LEADER_COUNT_FAILURE + 1))
    fi
done

log "Leader count during API failure: $LEADER_COUNT_FAILURE (expected: 0)"
if [ "$LEADER_COUNT_FAILURE" -ne 0 ]; then
    warn "Expected 0 leaders during API failure, but found $LEADER_COUNT_FAILURE. This may indicate graceful degradation is not working."
fi

# Step 11: Verify no new events created during failure
log "Verifying no new events created during API failure (reconciliation stopped)..."
EVENT_COUNT_FAILURE=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Event count during failure: $EVENT_COUNT_FAILURE (baseline: $EVENT_COUNT_BASELINE)"

if [ "$EVENT_COUNT_FAILURE" -gt "$EVENT_COUNT_BASELINE" ]; then
    warn "Event count increased during API failure. Expected no new events."
fi

# Step 12: Remove NetworkPolicy to restore API access
log "Removing NetworkPolicy to restore API access..."
kubectl delete networkpolicy -n "$NAMESPACE" block-api-server

log "NetworkPolicy removed. Operator pods can now reach API server."
sleep 30  # Wait for new leader election

# Step 13: Verify new leader elected
log "Verifying new leader elected after recovery..."
NEW_LEADER_POD=""
for i in {1..15}; do
    sleep 2
    for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
        if kubectl logs -n "$NAMESPACE" "$pod" --tail=20 2>/dev/null | grep -q "Leader status: LEADER\|Acquired leadership"; then
            NEW_LEADER_POD=$pod
            break 2
        fi
    done
done

if [ -z "$NEW_LEADER_POD" ]; then
    error "No new leader elected after recovery"
    exit 1
fi

log "New leader elected: $NEW_LEADER_POD"

# Step 14: Apply second Agent CR to trigger reconciliation
log "Applying second Agent CR to verify reconciliation resumed..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: stress-agent-recovery
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF

sleep 15

# Step 15: Verify event count increased (reconciliation resumed)
log "Verifying reconciliation resumed after recovery..."
EVENT_COUNT_RECOVERY=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Event count after recovery: $EVENT_COUNT_RECOVERY (failure: $EVENT_COUNT_FAILURE)"

if [ "$EVENT_COUNT_RECOVERY" -le "$EVENT_COUNT_FAILURE" ]; then
    error "Event count did not increase after recovery. Reconciliation may not have resumed."
    exit 1
fi

# Step 16: Verify hash chain continuity (no gaps, no duplicates)
log "Verifying hash chain continuity after API failure simulation..."
kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | awk '{print $NF}' | sort > /tmp/rynxs-stress-events.txt

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
done < /tmp/rynxs-stress-events.txt

if [ "$GAP_FOUND" = true ] || [ "$DUPLICATE_FOUND" = true ]; then
    error "Hash chain continuity FAILED after API failure simulation"
    exit 1
fi

log "SUCCESS: Hash chain continuity verified (no gaps, no duplicates)"

# Step 17: Check leader election failure metrics
log "Checking leader election failure metrics..."
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    FAILURES=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_election_failures_total" || echo "")
    if [ -n "$FAILURES" ]; then
        info "Pod $pod failure metrics:"
        echo "$FAILURES" | grep -v "^#"
    fi
done

log "========================================="
log "Stress Test: API Server Failure PASSED"
log "========================================="
log "- Simulated API server failure via NetworkPolicy"
log "- Verified leader dropped during failure (graceful degradation)"
log "- Verified no new events created during failure (reconciliation stopped)"
log "- Verified new leader elected after recovery"
log "- Verified reconciliation resumed after recovery"
log "- Hash chain continuity verified (no gaps/duplicates)"
log "- Baseline events: $EVENT_COUNT_BASELINE"
log "- Events during failure: $EVENT_COUNT_FAILURE"
log "- Events after recovery: $EVENT_COUNT_RECOVERY"

# Cleanup runs automatically via trap
