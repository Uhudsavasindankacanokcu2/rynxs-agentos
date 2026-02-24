# Rynxs Helm Chart

Kubernetes-native AI workforce orchestration platform.

## Installation

### Install CRDs (one-time)

```bash
kubectl apply -f ../../crds/
```

### Install Rynxs

```bash
helm install rynxs . -n universe --create-namespace
```

### Upgrade

```bash
helm upgrade rynxs . -n universe
```

### Uninstall

```bash
helm uninstall rynxs -n universe
kubectl delete -f ../../crds/
```

## Configuration

Key values:

```yaml
operator:
  image:
    repository: ghcr.io/your-org/rynxs-operator
    tag: v1.0.0
  resources:
    limits:
      cpu: 500m
      memory: 512Mi

minio:
  enabled: true
  persistence:
    size: 10Gi
    storageClass: "fast-ssd"

networkPolicy:
  enabled: true

gvisor:
  enabled: false
```

See `values.yaml` for full configuration options.

## Examples

Deploy with custom values:

```bash
helm install rynxs . -f custom-values.yaml
```

Enable gVisor:

```bash
helm install rynxs . --set gvisor.enabled=true
```

Use specific operator version:

```bash
helm install rynxs . \
  --set operator.image.tag=v1.0.0
```

## Testing

Lint chart:

```bash
helm lint .
```

Template and validate:

```bash
helm template rynxs . | kubectl apply --dry-run=client -f -
```

Install in test mode:

```bash
helm install rynxs . --dry-run --debug
```
