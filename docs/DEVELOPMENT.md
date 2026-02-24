# Development Guide

This guide covers local development setup for Rynxs.

## Prerequisites

- Python 3.10+
- Docker
- kubectl
- kind or minikube (for local cluster)
- make (optional)

## Repository Structure

```
rynxs-agentos/
├── operator/                    # Kubernetes operator
│   └── universe_operator/
│       ├── main.py             # kopf entry point
│       ├── reconcile.py        # reconciliation logic
│       └── controllers/
│           └── binding.py      # consciousness binding
├── agent-runtime/              # Agent execution runtime
│   └── universe_agent/
│       ├── runtime.py          # main event loop
│       ├── workspace.py        # workspace abstraction
│       ├── policy.py           # policy enforcement
│       ├── tools/              # tool subsystem
│       └── controllers/        # universe model controllers
├── crds/                       # CRD definitions
├── deploy/kustomize/base/      # base deployment manifests
└── docs/                       # documentation
```

## Setting Up Local Development

### 1. Clone Repository

```bash
git clone https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos.git
cd rynxs-agentos
```

### 2. Install Python Dependencies

Operator dependencies:

```bash
cd operator
pip install -r requirements.txt
```

Runtime dependencies:

```bash
cd agent-runtime
pip install -r requirements.txt
```

### 3. Create Local Cluster

Using kind:

```bash
kind create cluster --name rynxs-dev
kubectl cluster-info --context kind-rynxs-dev
```

Using minikube:

```bash
minikube start --profile rynxs-dev
kubectl config use-context rynxs-dev
```

### 4. Install CRDs

```bash
kubectl apply -f crds/
```

### 5. Deploy Dependencies

```bash
kubectl apply -k deploy/kustomize/base
```

## Developing the Operator

### Local Operator Development

Run operator locally (outside cluster):

```bash
cd operator
export KUBECONFIG=~/.kube/config
kopf run universe_operator/main.py --verbose
```

This watches the cluster and reconciles Agent CRDs.

### Building Operator Image

```bash
cd operator
docker build -t rynxs-operator:dev .
kind load docker-image rynxs-operator:dev --name rynxs-dev
```

Update deployment:

```bash
kubectl set image deployment/rynxs-operator -n universe \
  operator=rynxs-operator:dev
```

### Operator Code Structure

Main reconciliation flow:

```python
@kopf.on.create('universe.ai', 'v1alpha1', 'agents')
@kopf.on.update('universe.ai', 'v1alpha1', 'agents')
def agent_reconcile(spec, name, namespace, logger, **_):
    ensure_agent_runtime(agent_name=name, namespace=namespace,
                        agent_spec=spec, logger=logger)
```

To add new reconciliation logic:

1. Edit `operator/universe_operator/reconcile.py`
2. Add new Kubernetes resources (Deployment, Service, etc.)
3. Test locally with `kopf run`
4. Build and deploy new image

## Developing the Runtime

### Local Runtime Development

Run runtime locally (requires workspace directory):

```bash
cd agent-runtime
mkdir -p /tmp/workspace
export AGENT_NAME=test-agent
export AGENT_NAMESPACE=universe
export WORKSPACE_PATH=/tmp/workspace
python -m universe_agent.runtime
```

### Building Runtime Image

```bash
cd agent-runtime
docker build -t universe-agent-runtime:dev .
kind load docker-image universe-agent-runtime:dev --name rynxs-dev
```

Update agent spec:

```yaml
spec:
  image:
    repository: universe-agent-runtime
    tag: dev
```

### Runtime Code Structure

Main event loop:

```python
# Initialize
workspace = Workspace("/workspace")
policy = UniversePolicy(agent_spec)
lifecycle = EntityLifecycle(workspace, memory)

# Birth
lifecycle.birth()

# Main loop
while True:
    lifecycle.awake_loop()
    zones.update_memberships(consciousness)

    # Process inbox
    for line in inbox.readlines():
        task = json.loads(line)
        # Execute tools, write to outbox
```

To add new tools:

1. Edit `agent-runtime/universe_agent/tools/registry.py`
2. Add tool definition with OpenAI function schema
3. Implement tool execution in `agent-runtime/universe_agent/tools/runner.py`
4. Test with local runtime

## Testing

### Unit Tests

Run operator tests:

```bash
cd operator
pytest tests/
```

Run runtime tests:

```bash
cd agent-runtime
pytest tests/
```

### Integration Tests

Deploy test agent:

```bash
kubectl apply -f docs/examples/agent.yaml
```

Send test task:

```bash
POD=$(kubectl get pods -n universe -l app=universe-agent -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n universe $POD -- sh -c 'echo "{\"text\":\"test task\"}" >> /workspace/inbox.jsonl'
```

Check logs:

```bash
kubectl logs -n universe $POD -f
```

Verify audit:

```bash
kubectl exec -n universe $POD -- cat /workspace/audit.jsonl
```

### E2E Tests

Full cluster test:

```bash
# Deploy full stack
kubectl apply -k deploy/kustomize/base
kubectl apply -f docs/examples/universe.yaml
kubectl apply -f docs/examples/agent.yaml

# Wait for agent to be ready
kubectl wait --for=condition=ready pod -l app=universe-agent -n universe --timeout=60s

# Send task
POD=$(kubectl get pods -n universe -l app=universe-agent -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n universe $POD -- sh -c 'echo "{\"text\":\"run uname -a\"}" >> /workspace/inbox.jsonl'

# Verify sandbox job was created
sleep 5
kubectl get jobs -n universe | grep sandbox-shell

# Verify audit trail
kubectl exec -n universe $POD -- tail -n 5 /workspace/audit.jsonl
```

## Debugging

### Operator Debugging

View operator logs:

```bash
kubectl logs -n universe -l app=rynxs-operator -f
```

Describe agent resource:

```bash
kubectl describe agent berkan-agent -n universe
```

Check agent status:

```bash
kubectl get agent berkan-agent -n universe -o jsonpath='{.status}'
```

### Runtime Debugging

View runtime logs:

```bash
kubectl logs -n universe -l app=universe-agent -f
```

Exec into runtime pod:

```bash
POD=$(kubectl get pods -n universe -l app=universe-agent -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it -n universe $POD -- sh
```

Check workspace contents:

```bash
kubectl exec -n universe $POD -- ls -la /workspace
```

Check audit log:

```bash
kubectl exec -n universe $POD -- cat /workspace/audit.jsonl
```

### Network Debugging

Test DNS resolution:

```bash
kubectl exec -n universe $POD -- nslookup minio.universe.svc.cluster.local
```

Test NetworkPolicy (should fail for denied endpoints):

```bash
kubectl exec -n universe $POD -- wget -O- http://google.com --timeout=5
```

## Code Style

### Python

Follow PEP 8:

```bash
# Format code
black operator/ agent-runtime/

# Lint
flake8 operator/ agent-runtime/

# Type check
mypy operator/ agent-runtime/
```

### YAML

Use 2-space indentation for Kubernetes manifests.

Validate manifests:

```bash
kubectl apply --dry-run=client -f manifest.yaml
```

## Contributing

1. Fork repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Make changes and test locally
4. Run tests: `pytest`
5. Commit changes: `git commit -m "feat: add new feature"`
6. Push branch: `git push origin feature/new-feature`
7. Create Pull Request

### Commit Message Format

Follow conventional commits:

- `feat: add new feature`
- `fix: fix bug`
- `docs: update documentation`
- `refactor: refactor code`
- `test: add tests`
- `chore: update dependencies`

## Release Process

1. Update version in code
2. Update CHANGELOG.md
3. Tag release: `git tag v1.0.0`
4. Build and push images:

```bash
docker build -t ghcr.io/your-org/rynxs-operator:v1.0.0 operator/
docker push ghcr.io/your-org/rynxs-operator:v1.0.0

docker build -t ghcr.io/your-org/rynxs-agent-runtime:v1.0.0 agent-runtime/
docker push ghcr.io/your-org/rynxs-agent-runtime:v1.0.0
```

5. Create GitHub release with changelog
6. Update documentation with new version

## Troubleshooting Development Issues

### CRD Not Found

```bash
kubectl apply -f crds/
```

### Operator Crash Loop

Check logs for Python errors:

```bash
kubectl logs -n universe -l app=rynxs-operator
```

Common issues:
- Missing RBAC permissions
- Invalid CRD spec
- Python dependency errors

### Agent Pod Not Starting

Check pod events:

```bash
kubectl describe pod -n universe -l app=universe-agent
```

Common issues:
- Image pull errors
- PVC mount failures
- SecurityContext violations
- RuntimeClass not available

### Sandbox Jobs Failing

Check job logs:

```bash
kubectl logs -n universe job/sandbox-shell-<id>
```

Common issues:
- NetworkPolicy blocking egress
- Command syntax errors
- TTL cleanup deleting job too quickly
