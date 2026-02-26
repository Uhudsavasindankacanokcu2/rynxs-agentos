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
# Install with default configuration
helm install rynxs ./helm/rynxs

# Install with custom values
helm install rynxs ./helm/rynxs --values custom-values.yaml

# Install in specific namespace
helm install rynxs ./helm/rynxs --namespace rynxs --create-namespace
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

## Upgrade

```bash
# Upgrade to new version
helm upgrade rynxs ./helm/rynxs

# Upgrade with custom values
helm upgrade rynxs ./helm/rynxs --values custom-values.yaml
```

**Note**: CRD upgrades are not managed by Helm. To upgrade CRDs, manually apply them:

```bash
kubectl apply -f crds/
```

## Uninstall

```bash
# Uninstall release
helm uninstall rynxs

# Clean up CRDs (if desired)
kubectl delete crd agents.universe.ai sessions.universe.ai universes.universe.ai
```

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
- [RBAC Permissions](../../docs/RBAC.md) (coming in E1.3)
- [MinIO Setup](../../docs/MINIO.md) (coming in E2)

## Support

For issues and feature requests, visit: https://github.com/rynxs/rynxs-agentos/issues

## License

MIT
