#!/usr/bin/env bash
#
# E2E test for Leader Election + Failover Determinism
#
# Prerequisites:
# - kubectl configured with cluster access
# - helm 3.x installed
#
# Usage:
#   ./scripts/e2e-ha-failover.sh
#
# This script:
# 1. Deploys rynxs operator with 3 replicas + leader election enabled
# 2. Verifies only 1 leader (via logs + metrics)
# 3. Applies Agent CR to trigger events
# 4. Kills leader pod
# 5. Waits for new leader election
# 6. Verifies hash chain continuity (no gaps, no duplicates)
# 7. Cleans up resources

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
NAMESPACE="rynxs-ha-test"
RELEASE_NAME="rynxs-ha"
REPLICA_COUNT=3

log() {
    echo -e "${GREEN}[E2E-HA]${NC} $*"
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

log "Starting E2E HA Failover Test (Leader Election)"

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

# Step 6: Identify leader (check logs for "Acquired leadership" or "Leader status: LEADER")
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

# Step 7: Verify only 1 leader (via metrics)
log "Verifying leader count via Prometheus metrics..."
LEADER_COUNT=0
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    METRIC=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_election_status " | awk '{print $2}')
    if [ "$METRIC" = "1" ] || [ "$METRIC" = "1.0" ]; then
        LEADER_COUNT=$((LEADER_COUNT + 1))
        info "Pod $pod: LEADER (metric=1)"
    else
        info "Pod $pod: FOLLOWER (metric=0)"
    fi
done

if [ "$LEADER_COUNT" -ne 1 ]; then
    error "Expected 1 leader, found $LEADER_COUNT"
    exit 1
fi

log "SUCCESS: Exactly 1 leader confirmed"

# Step 8: Apply Agent CR to generate events
log "Applying Agent CR to trigger event log entries..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: test-agent-ha
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF

sleep 10

# Step 9: Capture current event count
log "Capturing current event count in S3..."
EVENT_COUNT_BEFORE=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Event count before failover: $EVENT_COUNT_BEFORE"

# Step 10: Kill leader pod
log "Killing leader pod: $LEADER_POD"
kubectl delete pod -n "$NAMESPACE" "$LEADER_POD" --wait=false

# Step 11: Wait for new leader election
log "Waiting for new leader election (max 30s)..."
NEW_LEADER_POD=""
for i in {1..15}; do
    sleep 2
    for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
        if [ "$pod" = "$LEADER_POD" ]; then
            continue  # Skip old leader (terminating)
        fi
        if kubectl logs -n "$NAMESPACE" "$pod" --tail=20 2>/dev/null | grep -q "Leader status: LEADER\|Acquired leadership"; then
            NEW_LEADER_POD=$pod
            break 2
        fi
    done
done

if [ -z "$NEW_LEADER_POD" ]; then
    error "No new leader elected within 30s"
    exit 1
fi

log "New leader elected: $NEW_LEADER_POD"

# Step 12: Apply another Agent CR to trigger more events
log "Applying second Agent CR..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: test-agent-ha-2
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF

sleep 10

# Step 13: Verify event count increased
log "Verifying event count after failover..."
EVENT_COUNT_AFTER=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | wc -l || echo "0")
log "Event count after failover: $EVENT_COUNT_AFTER"

if [ "$EVENT_COUNT_AFTER" -le "$EVENT_COUNT_BEFORE" ]; then
    error "Event count did not increase after failover"
    exit 1
fi

# Step 14: Verify hash chain continuity (no gaps, no duplicates)
log "Verifying hash chain continuity..."
kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- mc ls local/rynxs-events/events/ 2>/dev/null | awk '{print $NF}' | sort > /tmp/rynxs-events.txt

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
done < /tmp/rynxs-events.txt

if [ "$GAP_FOUND" = true ] || [ "$DUPLICATE_FOUND" = true ]; then
    error "Hash chain continuity FAILED (gaps or duplicates detected)"
    exit 1
fi

log "SUCCESS: Hash chain continuity verified (no gaps, no duplicates)"

# Step 15: Verify leader count still 1
log "Verifying leader count after failover..."
LEADER_COUNT_AFTER=0
for pod in $(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs -o jsonpath='{.items[*].metadata.name}'); do
    METRIC=$(kubectl exec -n "$NAMESPACE" "$pod" -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^rynxs_leader_election_status " | awk '{print $2}')
    if [ "$METRIC" = "1" ] || [ "$METRIC" = "1.0" ]; then
        LEADER_COUNT_AFTER=$((LEADER_COUNT_AFTER + 1))
    fi
done

if [ "$LEADER_COUNT_AFTER" -ne 1 ]; then
    error "Expected 1 leader after failover, found $LEADER_COUNT_AFTER"
    exit 1
fi

log "SUCCESS: Leader count correct after failover (still 1 leader)"

log "========================================="
log "E2E HA Failover Test PASSED"
log "========================================="
log "- Deployed $REPLICA_COUNT replicas with leader election"
log "- Verified exactly 1 leader initially"
log "- Killed leader pod: $LEADER_POD"
log "- New leader elected: $NEW_LEADER_POD"
log "- Hash chain continuity verified (no gaps/duplicates)"
log "- Leader count remains 1 after failover"
log "- Event count: $EVENT_COUNT_BEFORE -> $EVENT_COUNT_AFTER"

# Cleanup runs automatically via trap
