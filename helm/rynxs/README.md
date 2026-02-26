# Rynxs Helm Chart

Deterministic execution engine operator for Kubernetes (rynxs-agentos).

## Overview

Rynxs provides a deterministic, replayable, and auditable execution engine for AI workforce orchestration on Kubernetes. This Helm chart deploys the rynxs operator with production-ready configuration.

## Features

- **Deterministic Execution**: Event-sourced architecture with hash-chained events
- **Replayability**: Exact state reconstruction from event log
- **Auditability**: Cryptographically signed checkpoints
- **High Availability**: Leader election support for multi-replica deployments (E3)
- **Remote Storage**: S3-compatible event log storage with MinIO (E2)
- **Observability**: Prometheus metrics and structured logging (E4)

## Installation

### Quick Start

```bash
# Install with default configuration (includes CRDs)
helm install rynxs ./helm/rynxs

# Install with custom values
helm install rynxs ./helm/rynxs --values custom-values.yaml

# Install in specific namespace
helm install rynxs ./helm/rynxs --namespace rynxs --create-namespace

# Skip CRD installation (if CRDs are managed externally)
helm install rynxs ./helm/rynxs --skip-crds
```

### Verify Installation

```bash
# Check operator status
kubectl get pods -l app.kubernetes.io/name=rynxs

# View operator logs
kubectl logs -l app.kubernetes.io/name=rynxs

# Apply sample Agent CR
kubectl apply -f examples/agent-basic.yaml
```

## Configuration

See [values.yaml](values.yaml) for full configuration options.

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Operator image repository | `ghcr.io/rynxs/operator` |
| `image.tag` | Operator image tag | `v0.1.0` |
| `replicaCount` | Number of operator replicas | `1` |
| `persistence.enabled` | Enable persistent event log storage | `true` |
| `persistence.size` | PVC size for event log | `10Gi` |
| `leaderElection.enabled` | Enable leader election for HA | `false` |
| `logSink.type` | Event log storage type (file/s3) | `file` |
| `metrics.enabled` | Enable Prometheus metrics endpoint | `false` |

### Examples

#### High Availability Deployment

```yaml
# ha-values.yaml
replicaCount: 3
leaderElection:
  enabled: true
  leaseDuration: 15s
  renewDeadline: 10s
  retryPeriod: 2s
```

```bash
helm install rynxs ./helm/rynxs --values ha-values.yaml
```

#### S3 Remote Storage

**Option 1: Deploy with Built-in MinIO (Recommended for testing/dev)**

```yaml
# s3-minio-values.yaml
minio:
  enabled: true
  rootUser: minioadmin
  rootPassword: minioadmin  # Change in production!
  persistence:
    enabled: true
    size: 5Gi

logSink:
  type: s3
  s3:
    bucket: "rynxs-events"
    region: "us-east-1"
    accessKeySecret: "rynxs-s3-credentials"
    # endpoint auto-configured to MinIO service when minio.enabled=true
```

```bash
# Create S3 credentials secret
kubectl create secret generic rynxs-s3-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
  --from-literal=AWS_SECRET_ACCESS_KEY=minioadmin \
  --namespace rynxs

# Install with MinIO + S3 storage
helm install rynxs ./helm/rynxs --values s3-minio-values.yaml --namespace rynxs --create-namespace

# Wait for MinIO and operator pods
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=rynxs -n rynxs --timeout=120s
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=minio -n rynxs --timeout=120s

# Create bucket (exec into MinIO pod)
MINIO_POD=$(kubectl get pod -n rynxs -l app.kubernetes.io/component=minio -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n rynxs $MINIO_POD -- sh -c "
    wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /tmp/mc && chmod +x /tmp/mc
    /tmp/mc alias set local http://localhost:9000 minioadmin minioadmin
    /tmp/mc mb local/rynxs-events --ignore-existing
"

# Verify S3 event storage
kubectl apply -f examples/agent-basic.yaml -n rynxs
sleep 10
kubectl exec -n rynxs $MINIO_POD -- /tmp/mc ls local/rynxs-events/events/
```

**Option 2: External S3 / MinIO (Production)**

```yaml
# s3-external-values.yaml
logSink:
  type: s3
  s3:
    endpoint: "https://s3.us-east-1.amazonaws.com"  # Or MinIO URL
    bucket: "rynxs-events-prod"
    region: "us-east-1"
    accessKeySecret: "rynxs-s3-credentials"
```

```bash
# Create S3 credentials secret (use IAM user credentials)
kubectl create secret generic rynxs-s3-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=AKIA... \
  --from-literal=AWS_SECRET_ACCESS_KEY=secret... \
  --namespace rynxs

# Ensure bucket exists
aws s3 mb s3://rynxs-events-prod --region us-east-1

# Install with external S3 storage
helm install rynxs ./helm/rynxs --values s3-external-values.yaml --namespace rynxs
```

**Verify S3 Storage**:

```bash
# Check operator logs for S3 connection
kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=50 | grep -i s3

# List event objects (MinIO)
kubectl exec -n rynxs $MINIO_POD -- /tmp/mc ls local/rynxs-events/events/

# List event objects (AWS S3)
aws s3 ls s3://rynxs-events-prod/events/
```

#### Observability (Metrics + Structured Logging)

**Vanilla Prometheus (annotation-based discovery)**:

```yaml
# observability-values.yaml
metrics:
  enabled: true
  port: 8080
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"

logging:
  level: INFO
  format: json  # Structured JSON logs with trace_id
```

**Prometheus Operator (ServiceMonitor)**:

```yaml
# observability-values.yaml
metrics:
  enabled: true
  port: 8080
  serviceMonitor:
    enabled: true
    interval: 30s
    scrapeTimeout: 10s
    labels:
      prometheus: kube-prometheus  # Match your Prometheus selector

logging:
  level: INFO
  format: json
```

**Important Notes**:
- **Metrics path**: Currently fixed at `/metrics` (limitation of `prometheus_client.start_http_server()`). The `metrics.path` value is for documentation/future extensibility.
- **ServiceMonitor troubleshooting**: If Prometheus Operator doesn't scrape, check [official troubleshooting guide](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/troubleshooting.md).
- **Security**: Metrics endpoint is HTTP-only by default. For TLS, use a service mesh (Istio/Linkerd) or configure `prometheus_client` HTTPS options in a custom build.

```bash
# Install with observability enabled
helm install rynxs ./helm/rynxs --values observability-values.yaml

# Verify metrics endpoint
kubectl port-forward -n rynxs svc/rynxs-metrics 8080:8080
curl http://localhost:8080/metrics

# View structured JSON logs
kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=50
```

**Available Metrics**:
- `rynxs_events_total` (Counter): Total events appended to event log (label: `event_type`)
- `rynxs_reconcile_duration_seconds` (Histogram): Reconcile operation duration (label: `resource_type`)
- `rynxs_leader_election_status` (Gauge): Leader election status (1=leader, 0=follower)
- `rynxs_replay_duration_seconds` (Histogram): Event log replay duration
- `rynxs_checkpoint_create_duration_seconds` (Histogram): Checkpoint creation duration
- `rynxs_checkpoint_verify_failures_total` (Counter): Checkpoint verification failures

## Upgrade

### Upgrading the Chart

```bash
# Upgrade to new version
helm upgrade rynxs ./helm/rynxs

# Upgrade with custom values
helm upgrade rynxs ./helm/rynxs --values custom-values.yaml
```

### Upgrading CRDs

**Important**: Helm does not upgrade CRDs automatically. CRDs must be upgraded manually before upgrading the chart.

**Why?** Helm's `crds/` directory is special: CRDs are installed on `helm install` but are **not updated** on `helm upgrade`. This is intentional to prevent accidental breaking changes to existing custom resources.

**Upgrade Procedure**:

1. **First**, manually apply CRD updates:
   ```bash
   kubectl apply -f helm/rynxs/crds/
   ```

2. **Then**, upgrade the chart:
   ```bash
   helm upgrade rynxs ./helm/rynxs
   ```

**Verification**:
```bash
# Check CRD versions
kubectl get crd agents.universe.ai sessions.universe.ai -o yaml | grep "version:"

# Verify operator can reconcile resources
kubectl apply -f examples/agent-basic.yaml
kubectl get agents -n rynxs
```

**References**:
- [Helm CRD Best Practices](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/)
- [Kubernetes CRD Versioning](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/)

## Uninstall

```bash
# Uninstall release (removes operator, RBAC, Service, etc.)
helm uninstall rynxs
```

**Important Notes**:

1. **CRDs are NOT deleted**: `helm uninstall` does **not** delete CRDs. This is intentional to prevent accidental data loss (custom resources would be cascade-deleted if CRDs are removed).

2. **PVC behavior**: By default, the event log PVC is deleted on uninstall. To preserve event logs across uninstalls:
   ```yaml
   # values.yaml
   persistence:
     keepOnUninstall: true  # Adds helm.sh/resource-policy: keep annotation
   ```
   **Warning**: If `keepOnUninstall: true`, the PVC will become orphaned and may cause a name collision on reinstall. You must manually delete the PVC or use a different release name. See [Helm documentation](https://helm.sh/docs/howto/charts_tips_and_tricks/#tell-helm-not-to-uninstall-a-resource) for details.

**To completely remove CRDs** (⚠️ this deletes all custom resources):

```bash
# WARNING: This will delete all Agents and Sessions in the cluster
kubectl delete crd agents.universe.ai sessions.universe.ai

# Verify deletion
kubectl get crd | grep universe.ai
```

**References**:
- [Helm CRD Deletion Behavior](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/#some-caveats-and-explanations)

## Requirements

- Kubernetes 1.24+
- Helm 3.x
- (Optional) S3-compatible storage for remote event log (MinIO, AWS S3, etc.)

## Development

### Lint Chart

```bash
helm lint helm/rynxs
```

### Render Templates

```bash
helm template rynxs helm/rynxs > rendered.yaml
```

### Dry Run Install

```bash
helm install rynxs ./helm/rynxs --dry-run --debug
```

**Note**: `--dry-run` has limitations with CRDs. The API server may not recognize custom resources during dry-run since CRDs are not actually created. For complete validation:

```bash
# 1. Render templates to file
helm template rynxs helm/rynxs > rendered.yaml

# 2. Validate with kubectl (client-side only)
kubectl apply --dry-run=client -f rendered.yaml

# 3. For server-side validation, install CRDs first
kubectl apply -f helm/rynxs/crds/
kubectl apply --dry-run=server -f rendered.yaml
```

## Architecture

Rynxs operator implements event-sourcing with deterministic state transitions:

```
Event Log (Append-Only)
         ↓
   Hash Chain Verification
         ↓
   Reducer (Pure Functions)
         ↓
   State Reconstruction
         ↓
   Kubernetes Resources (ConfigMap, PVC, Deployment, NetworkPolicy)
```

## Documentation

- [Architecture Overview](../../docs/ARCHITECTURE.md)
- [Determinism Proof](../../DETERMINISM_PROOF.md)
- [RBAC Permissions](../../docs/RBAC.md)
- [MinIO Setup](../../docs/MINIO.md) (coming in E2)

## Support

For issues and feature requests, visit: https://github.com/rynxs/rynxs-agentos/issues

## License

MIT
