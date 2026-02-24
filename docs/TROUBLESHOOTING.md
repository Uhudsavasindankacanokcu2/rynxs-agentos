# Troubleshooting Guide

Common issues and solutions for Rynxs deployment and operation.

## Installation Issues

### CRD Installation Fails

**Symptom:**
```
error: unable to recognize "crds/universe.ai_agents.yaml": no matches for kind "CustomResourceDefinition"
```

**Solution:**

Check Kubernetes version (requires 1.16+):
```bash
kubectl version --short
```

Verify CRD API version:
```bash
kubectl api-versions | grep apiextensions
```

Expected: `apiextensions.k8s.io/v1`

### Kustomize Build Fails

**Symptom:**
```
Error: accumulating resources: accumulation err='accumulating resources from '../../../crds': ...
```

**Solution:**

Verify path exists:
```bash
ls -la crds/
```

Check kustomization.yaml syntax:
```bash
kubectl kustomize deploy/kustomize/base --enable-alpha-plugins
```

Fix: Ensure `resources` paths are correct relative to kustomization.yaml location.

### NetworkPolicy Not Enforced

**Symptom:**
Agent can reach external endpoints despite deny-all policy.

**Solution:**

Check if CNI supports NetworkPolicy:
```bash
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
```

Supported CNIs: Calico, Cilium, Antrea, Weave Net (with Network Policy Controller).

Install Calico (example):
```bash
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml
```

Verify NetworkPolicy is applied:
```bash
kubectl get networkpolicy -n universe
```

## Operator Issues

### Operator Crash Loop

**Symptom:**
```bash
kubectl get pods -n universe -l app=rynxs-operator
NAME                              READY   STATUS             RESTARTS   AGE
rynxs-operator-7d9c8b5f6d-x4k2p   0/1     CrashLoopBackOff   5          3m
```

**Solution:**

Check logs:
```bash
kubectl logs -n universe -l app=rynxs-operator --tail=50
```

Common causes:

1. Missing RBAC permissions:
```bash
kubectl auth can-i create deployments --namespace=universe --as=system:serviceaccount:universe:rynxs-operator
```

Fix: Ensure ClusterRole and ClusterRoleBinding are applied.

2. Python dependency errors:
```
ModuleNotFoundError: No module named 'kopf'
```

Fix: Rebuild operator image with correct requirements.txt.

3. Kubernetes API connection issues:
```
urllib3.exceptions.MaxRetryError: HTTPSConnectionPool
```

Fix: Check ServiceAccount token and cluster connectivity.

### Agent Not Created

**Symptom:**
Applied Agent CR but no Deployment created.

**Solution:**

Check operator logs for reconciliation errors:
```bash
kubectl logs -n universe -l app=rynxs-operator | grep "agent_reconcile"
```

Describe Agent resource:
```bash
kubectl describe agent <agent-name> -n universe
```

Check for status conditions:
```bash
kubectl get agent <agent-name> -n universe -o jsonpath='{.status.conditions}'
```

Common causes:
- Image verification failed (if verify: true)
- Invalid agent spec format
- Operator not watching correct namespace

### Image Verification Fails

**Symptom:**
```
Agent status: ImageVerified=False, reason=VerificationFailed
```

**Solution:**

Check if cosign is available in operator:
```bash
kubectl exec -n universe <operator-pod> -- which cosign
```

Verify public key is mounted:
```bash
kubectl exec -n universe <operator-pod> -- cat /etc/cosign/cosign.pub
```

Test verification manually:
```bash
cosign verify --key cosign.pub ghcr.io/your-org/image:tag
```

Workaround: Disable verification temporarily:
```yaml
spec:
  image:
    verify: false
```

## Agent Runtime Issues

### Agent Pod Not Starting

**Symptom:**
```bash
kubectl get pods -n universe -l app=universe-agent
NAME                              READY   STATUS             RESTARTS   AGE
berkan-agent-runtime-xxx          0/1     ImagePullBackOff   0          2m
```

**Solution:**

Check pod events:
```bash
kubectl describe pod -n universe <pod-name>
```

Common causes:

1. Image pull errors:
```
Failed to pull image "universe-agent-runtime:dev": rpc error: code = Unknown desc = Error response from daemon: pull access denied
```

Fix: Use correct image registry, ensure credentials, or use `imagePullSecrets`.

2. PVC mount failures:
```
Unable to attach or mount volumes: unmounted volumes=[workspace]
```

Fix: Check PVC exists and is bound:
```bash
kubectl get pvc -n universe
```

3. RuntimeClass not found:
```
Warning  FailedCreatePodSandBox  RuntimeClass "gvisor" not found
```

Fix: Remove runtimeClassName or install gVisor:
```yaml
spec:
  template:
    spec:
      runtimeClassName: null  # or remove line
```

4. SecurityContext violations:
```
Error: container has runAsNonRoot and image has non-numeric user (root)
```

Fix: Update Dockerfile to use non-root user:
```dockerfile
USER 1000:1000
```

### Agent Not Processing Tasks

**Symptom:**
Sent task to inbox.jsonl but no response in outbox.jsonl.

**Solution:**

Check agent logs:
```bash
kubectl logs -n universe -l app=universe-agent -f
```

Verify inbox was written:
```bash
kubectl exec -n universe <pod-name> -- cat /workspace/inbox.jsonl
```

Common causes:

1. Invalid JSON in inbox:
```json
{"text": "task"}  # correct
{text: task}       # invalid
```

2. Policy blocking tool execution:
```
PermissionError: Tool 'sandbox.shell' not allowed by policy
```

Fix: Update agent spec:
```yaml
spec:
  tools:
    allow: ["sandbox.shell"]
```

3. LLM provider unreachable:
```
ConnectionError: Failed to connect to http://llm-proxy:8080
```

Fix: Check provider service exists and NetworkPolicy allows egress.

### Sandbox Jobs Fail

**Symptom:**
Sandbox jobs complete with error.

**Solution:**

List sandbox jobs:
```bash
kubectl get jobs -n universe | grep sandbox-shell
```

Check job logs:
```bash
kubectl logs -n universe job/<job-name>
```

Common causes:

1. Command syntax errors:
```bash
# Incorrect
sandbox.shell: "echo 'test"  # missing closing quote

# Correct
sandbox.shell: "echo 'test'"
```

2. NetworkPolicy blocking (expected behavior):
```bash
# This should fail due to deny-egress
wget http://google.com
```

3. TTL cleanup deleting job too quickly:

Jobs are deleted 3600s after completion. If you need logs, check immediately or disable TTL:
```python
# operator/universe_operator/reconcile.py
ttl_seconds_after_finished=None  # disable TTL
```

### Workspace Permissions Errors

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/workspace/state'
```

**Solution:**

Check PVC access mode:
```bash
kubectl get pvc -n universe -o jsonpath='{.items[*].spec.accessModes}'
```

Should be `ReadWriteOnce`.

Check pod security context:
```bash
kubectl get pod -n universe <pod-name> -o jsonpath='{.spec.securityContext}'
```

If running as wrong user, update deployment securityContext:
```yaml
securityContext:
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
```

## Memory and Lifecycle Issues

### Agent Respawn Not Working

**Symptom:**
Agent pod restarted but memory not restored.

**Solution:**

Check Volume layer exists:
```bash
kubectl exec -n universe <pod-name> -- cat /workspace/state/volume.json
```

Check audit log for RESPAWN event:
```bash
kubectl exec -n universe <pod-name> -- grep RESPAWN /workspace/audit.jsonl
```

If volume.json is empty, deep sleep may not have occurred. Trigger manually:
```python
lifecycle.deep_sleep()
```

### Deep Sleep Fails

**Symptom:**
```
FileExistsError: Snapshot already exists. Immutability enforced.
```

**Solution:**

Bucket layer enforces immutable snapshots. Each snapshot needs unique tag:
```python
# Incorrect: reusing tag
lifecycle.deep_sleep(tag="snapshot-1")
lifecycle.deep_sleep(tag="snapshot-1")  # fails

# Correct: unique tags
lifecycle.deep_sleep(tag=f"snapshot-{timestamp}")
```

Check existing snapshots:
```bash
kubectl exec -n universe <pod-name> -- ls /workspace/state/bucket/
```

### Memory Fragmentation Not Triggering Sleep

**Symptom:**
Agent running continuously without sleep cycles.

**Solution:**

Check sleep controller configuration:
```bash
kubectl exec -n universe <pod-name> -- grep sleep /config/agent.json
```

Verify fragmentation calculation in logs:
```bash
kubectl logs -n universe <pod-name> | grep fragmentation
```

Thresholds:
- Light sleep: fragmentation > 5.0
- Deep sleep: fragmentation > 15.0

If not triggering, verify stress estimation and RAM size calculations.

## Networking Issues

### DNS Resolution Fails

**Symptom:**
```
socket.gaierror: [Errno -2] Name or service not known
```

**Solution:**

Check DNS from pod:
```bash
kubectl exec -n universe <pod-name> -- nslookup kubernetes.default
```

Check NetworkPolicy allows DNS:
```bash
kubectl get networkpolicy -n universe agent-allow-egress -o yaml
```

Should include:
```yaml
egress:
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
    ports:
      - protocol: UDP
        port: 53
```

### MinIO Connection Refused

**Symptom:**
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solution:**

Check MinIO is running:
```bash
kubectl get pods -n universe -l app=minio
```

Check service exists:
```bash
kubectl get svc -n universe minio
```

Test connectivity:
```bash
kubectl exec -n universe <agent-pod> -- wget -O- http://minio.universe.svc.cluster.local:9000/minio/health/live
```

Check NetworkPolicy allows MinIO egress:
```bash
kubectl get networkpolicy -n universe agent-allow-egress -o yaml | grep -A 5 minio
```

## Performance Issues

### Agent Slow to Respond

**Solution:**

Check resource limits:
```bash
kubectl top pod -n universe <pod-name>
```

Increase limits in operator code:
```python
resources=client.V1ResourceRequirements(
    limits={"cpu": "4", "memory": "8Gi"}
)
```

Check PVC performance:
```bash
kubectl get pvc -n universe -o jsonpath='{.items[*].spec.storageClassName}'
```

Use faster storage class (e.g., SSD-backed).

### Sandbox Jobs Slow

**Solution:**

Jobs run with minimal resources. Increase in sandbox runner:
```python
# agent-runtime/universe_agent/tools/sandbox_k8s.py
resources=client.V1ResourceRequirements(
    requests={"cpu": "1", "memory": "1Gi"}
)
```

## Monitoring and Observability

### No Logs Visible

**Solution:**

Check logging backend:
```bash
kubectl get pods -n kube-system | grep -E 'fluentd|fluent-bit|logging'
```

Get logs directly:
```bash
kubectl logs -n universe <pod-name> --tail=100
```

Stream logs:
```bash
kubectl logs -n universe <pod-name> -f
```

### Audit Log Missing

**Solution:**

Check workspace mount:
```bash
kubectl exec -n universe <pod-name> -- ls -la /workspace/
```

Verify audit.jsonl exists:
```bash
kubectl exec -n universe <pod-name> -- cat /workspace/audit.jsonl | tail -5
```

If missing, check runtime initialization:
```bash
kubectl logs -n universe <pod-name> | grep audit
```

## Getting Help

If none of these solutions work:

1. Collect diagnostics:
```bash
kubectl describe agent <agent-name> -n universe > agent.txt
kubectl logs -n universe -l app=rynxs-operator --tail=200 > operator-logs.txt
kubectl logs -n universe -l app=universe-agent --tail=200 > agent-logs.txt
kubectl get all -n universe > resources.txt
```

2. Open GitHub issue with:
   - Kubernetes version
   - Rynxs version
   - Diagnostic files
   - Steps to reproduce

3. Check existing issues: https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos/issues
