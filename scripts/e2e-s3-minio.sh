#!/usr/bin/env bash
#
# E2E test for S3EventStore with MinIO
#
# Prerequisites:
# - kubectl configured with cluster access (minikube/kind/etc)
# - helm 3.x installed
#
# Usage:
#   ./scripts/e2e-s3-minio.sh
#
# This script:
# 1. Deploys MinIO via Helm chart
# 2. Creates S3 credentials secret
# 3. Deploys rynxs operator with S3 event store
# 4. Applies example Agent CR
# 5. Verifies S3 objects created (event log)
# 6. Cleans up resources

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="rynxs-e2e"
RELEASE_NAME="rynxs-test"
BUCKET_NAME="rynxs-events"
MINIO_ROOT_USER="minioadmin"
MINIO_ROOT_PASSWORD="minioadmin"

log() {
    echo -e "${GREEN}[E2E]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

cleanup() {
    log "Cleaning up resources..."
    helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete namespace "$NAMESPACE" --wait=false 2>/dev/null || true
    log "Cleanup complete"
}

# Trap EXIT to cleanup
trap cleanup EXIT

log "Starting E2E test for S3EventStore with MinIO"

# Step 1: Create namespace
log "Creating namespace: $NAMESPACE"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Step 2: Create S3 credentials secret
log "Creating S3 credentials secret"
kubectl create secret generic rynxs-s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD" \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

# Step 3: Deploy rynxs operator with MinIO + S3 store
log "Deploying rynxs operator with MinIO and S3 event store"
helm install "$RELEASE_NAME" ./helm/rynxs \
    --namespace="$NAMESPACE" \
    --set minio.enabled=true \
    --set minio.rootUser="$MINIO_ROOT_USER" \
    --set minio.rootPassword="$MINIO_ROOT_PASSWORD" \
    --set logSink.type=s3 \
    --set logSink.s3.bucket="$BUCKET_NAME" \
    --set logSink.s3.region=us-east-1 \
    --set logSink.s3.accessKeySecret=rynxs-s3-credentials \
    --wait \
    --timeout=5m

# Step 4: Wait for operator pod ready
log "Waiting for operator pod to be ready..."
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=rynxs \
    -n "$NAMESPACE" \
    --timeout=120s

# Step 5: Wait for MinIO pod ready
log "Waiting for MinIO pod to be ready..."
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/component=minio \
    -n "$NAMESPACE" \
    --timeout=120s

# Step 6: Create MinIO bucket (using kubectl exec with mc)
log "Creating S3 bucket: $BUCKET_NAME"
MINIO_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/component=minio -o jsonpath='{.items[0].metadata.name}')

# Install mc (MinIO client) in MinIO pod if not present
kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
    command -v mc >/dev/null 2>&1 || wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /tmp/mc && chmod +x /tmp/mc && mv /tmp/mc /usr/local/bin/mc
    mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
    mc mb local/$BUCKET_NAME --ignore-existing
" || warn "Bucket creation may have failed (might already exist)"

# Step 7: Restart operator to trigger bucket creation check
log "Restarting operator to apply S3 config..."
kubectl rollout restart deployment -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs
kubectl rollout status deployment -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs --timeout=120s

# Step 8: Check operator logs for S3 connection
log "Checking operator logs for S3 initialization..."
sleep 5
kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs --tail=50 | grep -i "s3\|minio\|event_store" || warn "No S3 logs found yet"

# Step 9: Apply example Agent CR
log "Applying example Agent CR..."
cat <<EOF | kubectl apply -n "$NAMESPACE" -f -
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: test-agent-s3
spec:
  role: sandbox
  resources:
    cpu: "100m"
    memory: "128Mi"
  image: "busybox:latest"
  command: ["sleep", "infinity"]
EOF

# Step 10: Wait for reconciliation
log "Waiting for reconciliation (30s)..."
sleep 30

# Step 11: Verify S3 objects created
log "Verifying S3 event objects..."
EVENT_COUNT=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
    mc ls local/$BUCKET_NAME/events/ 2>/dev/null | wc -l
" || echo "0")

if [ "$EVENT_COUNT" -gt 0 ]; then
    log "SUCCESS: Found $EVENT_COUNT event objects in S3"

    # Show first few events
    log "Listing event objects:"
    kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
        mc ls local/$BUCKET_NAME/events/ | head -10
    "

    # Show content of first event
    log "Content of first event (0000000000.json):"
    kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
        mc cat local/$BUCKET_NAME/events/0000000000.json 2>/dev/null || echo 'Event not found'
    " | head -20
else
    error "FAILED: No event objects found in S3 bucket"
    error "Checking operator logs for errors:"
    kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/name=rynxs --tail=100
    exit 1
fi

# Step 12: Verify hash chain (check if events are valid JSON with prev_hash/event_hash)
log "Verifying hash chain structure..."
FIRST_EVENT=$(kubectl exec -n "$NAMESPACE" "$MINIO_POD" -- sh -c "
    mc cat local/$BUCKET_NAME/events/0000000000.json 2>/dev/null || echo '{}'
")

if echo "$FIRST_EVENT" | jq -e '.prev_hash and .event_hash and .event' >/dev/null 2>&1; then
    log "SUCCESS: Event structure valid (prev_hash, event_hash, event fields present)"
    echo "$FIRST_EVENT" | jq '{ prev_hash, event_hash, event: { type: .event.type, aggregate_id: .event.aggregate_id, seq: .event.seq } }'
else
    error "FAILED: Event structure invalid"
    echo "$FIRST_EVENT"
    exit 1
fi

# Step 13: Check operator status
log "Checking operator status..."
kubectl get pods -n "$NAMESPACE"
kubectl get agents -n "$NAMESPACE"

log "========================================="
log "E2E test PASSED"
log "========================================="
log "- MinIO deployed and accessible"
log "- S3 bucket created: $BUCKET_NAME"
log "- Operator writing events to S3"
log "- Hash chain structure validated"
log "- Event count: $EVENT_COUNT"

# Cleanup will run automatically via trap
