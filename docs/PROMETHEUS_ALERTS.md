# Prometheus Alerts for Rynxs Operator

Critical alerts for production HA deployment (E4.4).

## Alert Definitions

### 1. RynxsNoLeader

**Severity**: Critical
**Purpose**: Detect when no operator pod holds leadership for extended period

```yaml
- alert: RynxsNoLeader
  expr: sum(rynxs_leader_election_status) == 0
  for: 2m
  labels:
    severity: critical
    component: rynxs-operator
  annotations:
    summary: "No rynxs operator leader elected"
    description: "No operator pod has held leadership for 2 minutes. Reconciliation is stopped. Check operator logs and lease status."
    runbook_url: "https://github.com/rynxs/rynxs-agentos/blob/main/docs/PROMETHEUS_ALERTS.md#runbook-rynxsnoleader"
```

**Threshold Rationale**:
- `for: 2m` = 2× default leaseDurationSeconds (30s)
- Ensures alert fires only after multiple election cycles fail
- Avoids false positives during pod restarts

**Expected Behavior**:
- Healthy cluster: `sum(rynxs_leader_election_status) == 1` (exactly 1 leader)
- During failover: Brief drop to 0 (< leaseDurationSeconds), then recovery
- Alerting condition: Sustained 0 for > 2m

---

### 2. RynxsLeaderFlap

**Severity**: Warning
**Purpose**: Detect excessive leader transitions (instability)

```yaml
- alert: RynxsLeaderFlap
  expr: increase(rynxs_leader_transitions_total[5m]) > 3
  for: 5m
  labels:
    severity: warning
    component: rynxs-operator
  annotations:
    summary: "Rynxs operator leader flapping detected"
    description: "Leader transitions increased by {{ $value }} in the last 5 minutes. Expected: ≤1 (rolling update). Check network stability, API server health, and pod crashloops."
    runbook_url: "https://github.com/rynxs/rynxs-agentos/blob/main/docs/PROMETHEUS_ALERTS.md#runbook-rynxsleaderflap"
```

**Threshold Rationale**:
- Normal: 0-1 transitions per 5 minutes (e.g., rolling update)
- Warning: >3 transitions in 5 minutes = flapping
- `for: 5m` ensures sustained flapping, not transient blips
- `increase()` counts absolute transitions (less noisy than `rate()`)

**Expected Values**:
- `rynxs_leader_transitions_total{event="acquired"}` = total acquisitions
- `rynxs_leader_transitions_total{event="lost"}` = total losses
- Increase should be 0-1 in stable cluster, 1-2 during rolling updates

---

### 3. RynxsLeaderElectionFailuresHigh

**Severity**: Warning
**Purpose**: Detect API errors or conflict retry exhaustion

```yaml
- alert: RynxsLeaderElectionFailuresHigh
  expr: rate(rynxs_leader_election_failures_total[5m]) > 0.05
  for: 5m
  labels:
    severity: warning
    component: rynxs-operator
  annotations:
    summary: "High rate of rynxs leader election failures"
    description: "Leader election failure rate is {{ $value | humanize }}/sec. Check API server health, RBAC permissions, and operator logs for 409 conflicts or network errors."
    runbook_url: "https://github.com/rynxs/rynxs-agentos/blob/main/docs/PROMETHEUS_ALERTS.md#runbook-rynxsleaderelectionfailureshigh"
```

**Failure Reasons** (label: `reason`):
- `api_error`: Kubernetes API failure (500, 503, timeout)
- `conflict_retries_exhausted`: 409 Conflict after 3 retries (resourceVersion mismatch)
- `lost_lease_during_renew`: Another pod took lease during renew
- `lost_takeover_race`: Another pod won takeover race
- `api_error_during_retry`: API failure during retry fresh read

---

### 4. RynxsReplayDurationHigh

**Severity**: Warning
**Purpose**: Detect slow event log replay (performance degradation)

```yaml
- alert: RynxsReplayDurationHigh
  expr: histogram_quantile(0.95, rate(rynxs_replay_duration_seconds_bucket[5m])) > 10
  for: 10m
  labels:
    severity: warning
    component: rynxs-operator
  annotations:
    summary: "Rynxs event log replay duration high"
    description: "P95 replay duration is {{ $value | humanize }} seconds (expected <5s). Event log may be growing too large. Consider implementing snapshot/compaction."
    runbook_url: "https://github.com/rynxs/rynxs-agentos/blob/main/docs/PROMETHEUS_ALERTS.md#runbook-rynxsreplaydurationhigh"
```

**Threshold Rationale**:
- Normal: <5s for ~10k events
- Warning: >10s p95 indicates growth beyond optimal range
- `for: 10m` ensures sustained slowness

---

## Runbooks

### Runbook: RynxsNoLeader

**Problem**: No operator pod is the leader. Reconciliation stopped.

**Diagnosis**:

1. **Check operator pod status**:
   ```bash
   kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs
   ```
   - Are all pods CrashLoopBackOff or Pending?
   - Are pods running but leader election failing?

2. **Check leader election logs**:
   ```bash
   kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=50 | grep -i leader
   ```
   Look for:
   - "Leader election error: ..." (API errors)
   - "conflict_retries_exhausted" (409 conflicts)
   - "RBAC Forbidden" (permissions issue)

3. **Check Lease object**:
   ```bash
   kubectl get lease -n rynxs rynxs-operator-leader -o yaml
   ```
   - Does lease exist?
   - Is `spec.holderIdentity` set?
   - Is `spec.renewTime` recent (within leaseDurationSeconds)?

4. **Check RBAC**:
   ```bash
   kubectl describe clusterrole rynxs-operator | grep -A5 "coordination.k8s.io"
   ```
   - Verify `leases` resource has `get, create, update` verbs

**Resolution**:

- **If pods are CrashLooping**: Check pod logs for startup errors, fix issue, pods will restart and elect leader
- **If API server is down**: Leader election will resume when API recovers (designed behavior)
- **If RBAC missing**: Apply ClusterRole with leases permissions (see docs/RBAC.md)
- **If Lease is stuck**: Delete lease manually (new leader will be elected):
  ```bash
  kubectl delete lease -n rynxs rynxs-operator-leader
  ```

**False Positives**:
- During rolling update: Brief (<30s) period with no leader is normal
- Alert threshold (2m) should prevent this

---

### Runbook: RynxsLeaderFlap

**Problem**: Leader transitions happening too frequently (instability).

**Diagnosis**:

1. **Check transition rate by event type**:
   ```bash
   # Via Prometheus UI or curl
   curl http://prometheus:9090/api/v1/query?query='rate(rynxs_leader_transitions_total[5m])'
   ```
   - High `acquired` + `lost` = flapping
   - High `acquired` only = rapid failovers (pods crashing)

2. **Check operator pod restarts**:
   ```bash
   kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs -o json | jq '.items[] | {name: .metadata.name, restarts: .status.containerStatuses[0].restartCount}'
   ```
   - High restarts = pods crashing (check logs)

3. **Check network stability**:
   ```bash
   kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=100 | grep -i "api.*timeout\|connection refused"
   ```
   - API timeouts = network partition or API server overload

4. **Check API server health**:
   ```bash
   kubectl get --raw /healthz
   ```
   - If unhealthy, API server issues may cause lease read/write failures

**Resolution**:

- **If pods are crashlooping**: Fix crash root cause (check logs for panics, OOM, etc.)
- **If network issues**: Check CNI plugin logs, firewall rules, service mesh sidecar issues
- **If API server overloaded**: Scale API server, reduce reconcile frequency, or increase leaseDurationSeconds
- **If contention (multiple pods competing)**: This is rare but possible if leaseDurationSeconds is too low (increase from 30s to 60s)

**Mitigation**:
```yaml
# values.yaml - increase lease duration to reduce competition
leaderElection:
  enabled: true
  leaseDurationSeconds: 60  # was 30
  renewDeadlineSeconds: 40  # was 20
```

---

### Runbook: RynxsLeaderElectionFailuresHigh

**Problem**: High rate of leader election API failures or 409 conflicts.

**Diagnosis**:

1. **Check failure reasons**:
   ```bash
   # Via Prometheus UI
   rate(rynxs_leader_election_failures_total[5m]) by (reason)
   ```
   - `api_error`: API server failures (5xx)
   - `conflict_retries_exhausted`: ResourceVersion conflicts (high contention)

2. **Check API server logs** (if accessible):
   ```bash
   kubectl logs -n kube-system kube-apiserver-... | grep "coordination.k8s.io/leases"
   ```
   - Look for 409 Conflict, 500 Internal Server Error

3. **Check operator logs for detailed errors**:
   ```bash
   kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=100 | grep "Leader election error"
   ```

**Resolution**:

- **If `api_error` dominant**: API server issues (check API server health, load, etcd latency)
- **If `conflict_retries_exhausted` dominant**: High contention (too many operator replicas competing)
  - Check replica count: `kubectl get deployment -n rynxs rynxs-operator -o jsonpath='{.spec.replicas}'`
  - For most clusters, 3 replicas is sufficient. >5 replicas may cause contention.
  - Consider increasing leaseDurationSeconds to reduce retry frequency

---

### Runbook: RynxsReplayDurationHigh

**Problem**: Event log replay taking too long (>10s p95).

**Diagnosis**:

1. **Check event count in S3/file store**:
   ```bash
   # For S3 (MinIO)
   kubectl exec -n rynxs minio-pod -- mc ls local/rynxs-events/events/ | wc -l

   # For file store
   kubectl exec -n rynxs rynxs-operator-pod -- wc -l /var/lib/rynxs/logs/operator-events.log
   ```

2. **Check replay histogram**:
   ```bash
   # Via Prometheus UI
   histogram_quantile(0.95, rate(rynxs_replay_duration_seconds_bucket[5m]))
   ```
   - p50 vs p95: If p50 is low but p95 is high, occasional spikes (acceptable)
   - If both high: Sustained slowness (action needed)

**Resolution**:

- **Short-term**: Current implementation reads entire log on each reconcile. This is acceptable for <100k events.
- **Long-term** (if event count >100k): Implement snapshots/compaction:
  - Store periodic state snapshots (e.g., every 10k events)
  - Replay from latest snapshot + subsequent events
  - Reference: Event Sourcing Snapshot Pattern

**Workaround** (if urgently needed):
- Archive old events to separate bucket/file
- Restart operator with fresh log (lose replay capability for archived events)
- This breaks deterministic replay guarantee - only use in emergencies

---

## Deployment with Alerts

### Option 1: Prometheus Operator (Recommended)

Create `PrometheusRule` resource:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: rynxs-operator-alerts
  namespace: rynxs
  labels:
    prometheus: kube-prometheus  # Match your Prometheus selector
spec:
  groups:
    - name: rynxs-operator
      interval: 30s
      rules:
        - alert: RynxsNoLeader
          expr: sum(rynxs_leader_election_status) == 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "No rynxs operator leader elected"
            description: "No operator pod has held leadership for 2 minutes."

        - alert: RynxsLeaderFlap
          expr: increase(rynxs_leader_transitions_total[5m]) > 3
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Rynxs operator leader flapping"
            description: "Leader transitions increased by {{ $value }} in 5 minutes."

        - alert: RynxsLeaderElectionFailuresHigh
          expr: rate(rynxs_leader_election_failures_total[5m]) > 0.05
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High leader election failure rate"
            description: "Failure rate is {{ $value }}/sec."

        - alert: RynxsReplayDurationHigh
          expr: histogram_quantile(0.95, rate(rynxs_replay_duration_seconds_bucket[5m])) > 10
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "Event log replay duration high"
            description: "P95 replay duration is {{ $value }}s."
```

Apply:
```bash
kubectl apply -f prometheus-rules.yaml
```

Verify:
```bash
kubectl get prometheusrule -n rynxs rynxs-operator-alerts
```

### Option 2: Vanilla Prometheus

Add to `prometheus.yml`:

```yaml
rule_files:
  - /etc/prometheus/rules/rynxs-operator.yml
```

Create `/etc/prometheus/rules/rynxs-operator.yml`:

```yaml
groups:
  - name: rynxs-operator
    interval: 30s
    rules:
      # (same rules as above)
```

Reload Prometheus:
```bash
curl -X POST http://prometheus:9090/-/reload
```

---

## Testing Alerts

### Test RynxsNoLeader

Simulate: Scale operator to 0 replicas

```bash
kubectl scale deployment -n rynxs rynxs-operator --replicas=0
```

Expected:
- After 2 minutes: Alert fires (PENDING → FIRING)
- Metric: `sum(rynxs_leader_election_status) == 0`

Cleanup:
```bash
kubectl scale deployment -n rynxs rynxs-operator --replicas=3
```

### Test RynxsLeaderFlap

Simulate: Rapidly delete leader pod in loop

```bash
for i in {1..10}; do
  LEADER=$(kubectl get pod -n rynxs -l app.kubernetes.io/name=rynxs -o json | jq -r '.items[0].metadata.name')
  kubectl delete pod -n rynxs $LEADER --wait=false
  sleep 5
done
```

Expected:
- `rynxs_leader_transitions_total` increases rapidly
- After 5 minutes: Alert fires

### Test RynxsLeaderElectionFailuresHigh

Simulate: Break RBAC (remove leases permissions)

```bash
# Backup current ClusterRole
kubectl get clusterrole rynxs-operator -o yaml > clusterrole-backup.yaml

# Remove leases permissions
kubectl patch clusterrole rynxs-operator --type=json -p='[{"op": "remove", "path": "/rules/6"}]'
```

Expected:
- `rynxs_leader_election_failures_total{reason="api_error"}` increases
- After 5 minutes: Alert fires

Cleanup:
```bash
kubectl apply -f clusterrole-backup.yaml
```

---

## PodDisruptionBudget Edge Cases

### Warning: minAvailable >= replicaCount Can Block Drains

**Problem**: If `minAvailable` is set too high relative to `replicaCount`, node drains can become stuck.

**Example**:
```yaml
# values.yaml
replicaCount: 3
podDisruptionBudget:
  minAvailable: 3  # ❌ BAD: Cannot drain any node
```

**Symptom**:
```bash
kubectl drain node-1
# Output: cannot evict pod rynxs-operator-xxx: violates PodDisruptionBudget
```

**Why**: Kubernetes won't drain a node if it would violate PDB. With `minAvailable: 3` and `replicaCount: 3`, draining any node means only 2 pods remain → violates PDB.

**Correct Configuration**:
```yaml
# values.yaml
replicaCount: 3
podDisruptionBudget:
  minAvailable: 1  # ✅ GOOD: At least 1 pod always available
  # OR
  maxUnavailable: 2  # ✅ GOOD: At most 2 pods can be unavailable
```

**Rule of Thumb**:
- `minAvailable` should be `< replicaCount` (ideally `≤ ceil(replicaCount/2)`)
- For 3 replicas: `minAvailable: 1` or `maxUnavailable: 2`
- For 5 replicas: `minAvailable: 2` or `maxUnavailable: 3`

**Testing**:
```bash
# Verify PDB allows drains
kubectl get pdb -n rynxs rynxs-operator -o yaml
# Check: .status.disruptionsAllowed should be > 0

# Attempt drain (dry-run)
kubectl drain node-1 --dry-run=server --ignore-daemonsets
# Expected: No PDB violations
```

**References**:
- [Kubernetes PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [PDB Best Practices](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)

---

## References

- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Kubernetes Leader Election](https://kubernetes.io/blog/2016/01/simple-leader-election-with-kubernetes/)
- [RBAC Permissions](./RBAC.md)
- [HA Deployment Guide](../helm/rynxs/README.md#high-availability-deployment-leader-election)
- [PodDisruptionBudget Best Practices](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)
