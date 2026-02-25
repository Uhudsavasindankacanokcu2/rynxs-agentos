# Deployment Guide

This guide covers production deployment of Rynxs on Kubernetes clusters.

## Prerequisites

- Kubernetes 1.24+
- kubectl configured with cluster access
- CNI that supports NetworkPolicy (Calico, Cilium, Antrea, etc.)
- Optional: gVisor or Kata Containers for enhanced isolation

## Quick Deploy

### 1. Install CRDs

```bash
kubectl apply -f crds/
```

Verify CRDs are installed:

```bash
kubectl get crd | grep universe.ai
```

Expected output:
```
agents.universe.ai
sessions.universe.ai
universes.universe.ai
```

### 2. Deploy Base Infrastructure

```bash
kubectl apply -k deploy/kustomize/base
```

This creates:
- Namespace: `universe`
- Operator: `rynxs-operator`
- MinIO: object storage for agent snapshots
- NetworkPolicies: default-deny egress rules
- RuntimeClass: gVisor (if available)

Verify deployment:

```bash
kubectl get all -n universe
```

### 3. Create Universe

```bash
kubectl apply -f docs/examples/universe.yaml
```

Verify Universe exists:

```bash
kubectl get universe u0
```

### 4. Deploy Agent

```bash
kubectl apply -f docs/examples/agent.yaml
```

Verify agent runtime is running:

```bash
kubectl get pods -n universe -l app=universe-agent
```

## Production Configuration

### Container Images

Update operator and runtime images:

```yaml
# deploy/kustomize/overlays/production/kustomization.yaml
images:
  - name: ghcr.io/uhudsavasindankacanokcu2/rynxs-operator
    newTag: v1.0.0
  - name: universe-agent-runtime
    newName: ghcr.io/your-org/rynxs-agent-runtime
    newTag: v1.0.0
```

### Operator HA + Event Store (Recommended)

Use at least 2 replicas with leader election enabled:

```yaml
operator:
  kind: deployment
  replicaCount: 2
  leaderElection:
    enabled: true
  eventStore:
    persistence:
      enabled: true
    rotation:
      enabled: false
```

Notes:
- `leaderElection` keeps a single writer active while standby pods stay idle.
- `eventStore.persistence` mounts a PVC at `/var/log/rynxs` for durable logs.
- Set `operator.writerId` if you want a stable writer identity across restarts.

### StatefulSet + Stable Writer Identity (Enterprise)

For audit-grade writer identity, use a StatefulSet (pod names are stable across restarts):

```yaml
operator:
  kind: statefulset
  replicaCount: 3
  writerId: "" # default = POD_NAME (stable: <release>-operator-0/1/2)
  leaderElection:
    enabled: true
  eventStore:
    persistence:
      enabled: true
```

Notes:
- `writerId` empty → `POD_NAME` is used; with StatefulSet this is stable.
- MinIO sink CronJob is only wired for `deployment` mode in the default chart.

### Event Store Rotation + MinIO Sink (Optional)

Rotation is supported via segmented log files:

```yaml
operator:
  eventStore:
    rotation:
      enabled: true
      maxBytes: 52428800     # 50 MiB
      maxSegments: 20
    sink:
      minio:
        enabled: true
        endpoint: http://minio:9000
        bucket: rynxs-logs
        accessKey: minioadmin
        secretKey: minioadmin
        prefix: ""
```

Notes:
- Segments preserve hash-chain continuity across rotations.
- MinIO sink runs as a CronJob to mirror the log directory.

### Storage Classes

Configure PVC storage class for agent workspaces:

```yaml
# Agent spec
spec:
  workspace:
    size: "10Gi"
    storageClassName: "fast-ssd"
```

### Resource Limits

Set resource limits for agent pods (configured in operator):

```python
# operator/universe_operator/reconcile.py
resources=client.V1ResourceRequirements(
    requests={"cpu": "500m", "memory": "1Gi"},
    limits={"cpu": "2", "memory": "4Gi"}
)
```

### Image Verification

Enable cosign signature verification:

```yaml
# Agent spec
spec:
  image:
    repository: ghcr.io/your-org/rynxs-agent-runtime
    tag: v1.0.0
    verify: true
```

Operator must have cosign binary and public key at `/etc/cosign/cosign.pub`.

### NetworkPolicy Hardening

Tighten egress rules:

```yaml
# networkpolicy-agent-allow-egress.yaml
spec:
  podSelector:
    matchLabels:
      app: universe-agent
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
    - to:
        - podSelector:
            matchLabels:
              app: minio
      ports:
        - protocol: TCP
          port: 9000
```

### gVisor Runtime

Install gVisor on cluster nodes:

```bash
# On each node (example for containerd)
wget https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
chmod +x runsc
sudo mv runsc /usr/local/bin/

# Configure containerd
cat <<EOF | sudo tee -a /etc/containerd/config.toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
EOF

sudo systemctl restart containerd
```

Verify RuntimeClass:

```bash
kubectl get runtimeclass gvisor
```

### Pod Security Standards

Apply Pod Security Admission labels:

```bash
kubectl label namespace universe \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

## Multi-Tenant Deployment

Create separate namespaces per tenant:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: universe-tenant-a
  labels:
    tenant: tenant-a
---
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: agent-1
  namespace: universe-tenant-a
spec:
  # ... agent spec
```

## Monitoring

### Operator Logs

```bash
kubectl logs -n universe -l app=rynxs-operator -f
```

### Agent Runtime Logs

```bash
kubectl logs -n universe -l app=universe-agent -f
```

### Audit Logs

Access agent audit trail:

```bash
POD=$(kubectl get pods -n universe -l app=universe-agent -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n universe $POD -- cat /workspace/audit.jsonl
```

### Metrics

Operator exposes basic Kubernetes metrics. For detailed metrics:

```yaml
# Add Prometheus annotations to operator deployment
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"
```

## Backup and Recovery

### Agent Workspace Backup

PVCs should be backed up using Velero or similar:

```bash
velero backup create agent-workspaces \
  --selector app=universe-agent \
  --include-cluster-resources=false
```

### Deep Sleep Snapshots

Agent snapshots are stored in MinIO. Configure MinIO replication or backup:

```bash
mc mirror minio/universe s3://backup-bucket/universe
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## Scaling

### Horizontal Scaling

Deploy multiple agents:

```bash
for i in {1..10}; do
  kubectl apply -f - <<EOF
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: agent-$i
  namespace: universe
spec:
  # ... agent spec
EOF
done
```

### Vertical Scaling

Increase agent workspace size:

```yaml
spec:
  workspace:
    size: "100Gi"
```

Operator will create PVC with requested size.

## Security Hardening

1. Enable image verification
2. Use private container registry
3. Apply Pod Security Standards (restricted)
4. Enable gVisor/Kata runtime
5. Restrict NetworkPolicy egress to specific IPs
6. Rotate MinIO credentials regularly
7. Enable audit log shipping to SIEM
8. Use RBAC to limit operator permissions

## Upgrade

Rolling upgrade operator:

```bash
kubectl set image deployment/rynxs-operator -n universe \
  operator=ghcr.io/uhudsavasindankacanokcu2/rynxs-operator:v1.1.0
```

Agent runtime updates require agent recreation:

```bash
kubectl delete agent berkan-agent -n universe
# Update agent.yaml with new image
kubectl apply -f docs/examples/agent.yaml
```

## Cleanup

Remove all resources:

```bash
kubectl delete -k deploy/kustomize/base
kubectl delete -f crds/
```
