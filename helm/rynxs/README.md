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

```yaml
# s3-values.yaml
logSink:
  type: s3
  s3:
    enabled: true
    endpoint: "minio-service.rynxs.svc.cluster.local:9000"
    bucket: "rynxs-events"
    region: "us-east-1"
    accessKeySecret: "rynxs-s3-credentials"
```

```bash
# Create S3 credentials secret
kubectl create secret generic rynxs-s3-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
  --from-literal=AWS_SECRET_ACCESS_KEY=minioadmin

# Install with S3 storage
helm install rynxs ./helm/rynxs --values s3-values.yaml
```

#### Observability (Metrics + Structured Logging)

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
# Uninstall release (removes operator, RBAC, PVC, etc.)
helm uninstall rynxs
```

**Important**: `helm uninstall` does **not** delete CRDs. This is intentional to prevent accidental data loss (custom resources would be cascade-deleted if CRDs are removed).

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
