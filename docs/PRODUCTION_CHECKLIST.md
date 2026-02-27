# Production Deployment Checklist

Final validation checklist before deploying rynxs operator to production. This document should be executed **after** applying Helm chart to verify production-readiness.

## Risk Posture

**Status**: All critical red flags addressed ✅

**Remaining risk**: Controlled and observable
- Incident scenarios have forensic analysis tools (fencing tokens, event metadata)
- Runbooks document diagnosis and resolution procedures
- Multi-layered mitigation reduces probability of split-brain and data loss
- **No absolute guarantees** (distributed systems physics apply)

---

## Pre-Deployment Validation

### 1. S3 Bucket Policy Enforcement

**Objective**: Verify bucket policy enforces `If-None-Match` header for conditional writes.

**Commands**:

```bash
# 1.1: Check bucket policy uses correct condition key (s3:if-none-match)
aws s3api get-bucket-policy --bucket rynxs-events-prod \
  | jq -r '.Policy | fromjson | .Statement[0].Condition'

# Expected output:
# {
#   "Null": {
#     "s3:if-none-match": "false"
#   }
# }
```

**Validation Tests**:

```bash
# Test 1: Unconditional write (no If-None-Match header) → Should FAIL
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key validation/test-unconditional.json \
  --body /dev/null

# Expected: AccessDenied (403) or similar auth error
# If succeeds: Policy NOT enforcing (CRITICAL)

# Test 2: Conditional write → First write OK, second write fails
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key validation/test-conditional.json \
  --body /dev/null \
  --if-none-match '*'

# Expected: 200 OK (object created)

aws s3api put-object \
  --bucket rynxs-events-prod \
  --key validation/test-conditional.json \
  --body /dev/null \
  --if-none-match '*'

# Expected: 412 PreconditionFailed (object already exists)
# This proves append-only enforcement at S3 layer
```

**Pass Criteria**:
- ✅ Test 1 fails with AccessDenied (or similar auth error preventing write)
- ✅ Test 2 first write succeeds (200 OK)
- ✅ Test 2 second write fails (412 PreconditionFailed)

**If FAIL**: Review [S3_BUCKET_POLICY.md](S3_BUCKET_POLICY.md) and reapply policy.

---

### 2. Topology Spread (Multi-Zone HA)

**Objective**: Verify pods are distributed across availability zones with hard constraint.

**Commands**:

```bash
# 2.1: Check cluster has zone labels
kubectl get nodes -L topology.kubernetes.io/zone

# Expected: Each node shows zone label (us-east-1a, us-east-1b, etc.)
# If empty: Zone spread will fail (pods Pending)

# 2.2: Verify Deployment uses DoNotSchedule for zone spread
helm template rynxs ./helm/rynxs -f helm/rynxs/values-production.yaml \
  | yq '.items[] | select(.kind=="Deployment") | .spec.template.spec.topologySpreadConstraints[] | select(.topologyKey=="topology.kubernetes.io/zone")'

# Expected output:
# maxSkew: 1
# topologyKey: topology.kubernetes.io/zone
# whenUnsatisfiable: DoNotSchedule  ← HARD constraint
# labelSelector:
#   matchLabels:
#     app.kubernetes.io/name: rynxs

# Alternative (if yq not available):
helm template rynxs ./helm/rynxs -f helm/rynxs/values-production.yaml \
  | grep -A7 "topologyKey: topology.kubernetes.io/zone"

# 2.3: After deployment, verify pods spread across zones
kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs -o wide

kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,ZONE:.spec.nodeSelector

# Expected: Pods on nodes in different zones
```

**Pass Criteria**:
- ✅ Cluster nodes have `topology.kubernetes.io/zone` labels
- ✅ Deployment spec includes `whenUnsatisfiable: DoNotSchedule` for zone spread
- ✅ Deployed pods are distributed across at least 2 zones (for replicaCount=3)

**If FAIL**:
- No zone labels → Add labels or change `DoNotSchedule` to `ScheduleAnyway`
- Pods in same zone → Check cluster capacity in other zones

---

### 3. MinIO Image Pinned (Supply Chain Security)

**Objective**: Verify MinIO uses pinned image tag (not `latest`).

**Commands**:

```bash
# 3.1: Check MinIO image tag in Helm values
helm template rynxs ./helm/rynxs --set minio.enabled=true \
  | grep -A2 "image:" | grep -A1 "minio/minio"

# Expected output includes:
# image: minio/minio:RELEASE.2024-11-07T00-15-16Z

# More precise check (if multiple images in chart):
helm template rynxs ./helm/rynxs --set minio.enabled=true \
  | awk '/kind: Deployment/{p=0} /name: .*minio/{p=1} p && /image:/{print}'

# Expected: image: minio/minio:RELEASE.2024-11-07T00-15-16Z
```

**Pass Criteria**:
- ✅ MinIO image tag is **not** `latest`
- ✅ Tag is specific release (e.g., `RELEASE.2024-11-07T00-15-16Z`)

**If FAIL**: Update `helm/rynxs/values.yaml` with pinned tag.

---

### 4. PodDisruptionBudget Conditional Rendering

**Objective**: Verify PDB only renders when replicaCount > 1.

**Commands**:

```bash
# Test 1: replicaCount=1 → No PDB
helm template rynxs ./helm/rynxs --set replicaCount=1 \
  | grep -c "kind: PodDisruptionBudget"

# Expected: 0 (no PDB rendered)

# Test 2: replicaCount=2 → PDB renders
helm template rynxs ./helm/rynxs --set replicaCount=2 \
  | grep -c "kind: PodDisruptionBudget"

# Expected: 1 (PDB rendered)

# Test 3: replicaCount=3 → PDB renders
helm template rynxs ./helm/rynxs --set replicaCount=3 \
  | grep -c "kind: PodDisruptionBudget"

# Expected: 1 (PDB rendered)

# Verify PDB spec has correct minAvailable
helm template rynxs ./helm/rynxs --set replicaCount=3 \
  | yq '.items[] | select(.kind=="PodDisruptionBudget") | .spec.minAvailable'

# Expected: 1 (or check values-production.yaml setting)
```

**Pass Criteria**:
- ✅ replicaCount=1 → 0 PDBs
- ✅ replicaCount=2 → 1 PDB
- ✅ replicaCount=3 → 1 PDB
- ✅ `minAvailable` < `replicaCount` (e.g., minAvailable=1 for replicaCount=3)

**If FAIL**: Check template logic in `helm/rynxs/templates/poddisruptionbudget.yaml`.

---

### 5. Fencing Token Documentation (Forensics)

**Objective**: Verify fencing token is documented as forensic tool (not enforcement).

**Commands**:

```bash
# Check leader_election.py docstring mentions "forensic"
grep -i "forensic" operator/universe_operator/leader_election.py

# Expected output includes:
# "forensic markers for post-mortem split-brain analysis"
# "What fencing tokens DO NOT do:"

# Verify fencing token is added to event metadata
grep -A5 "get_fencing_token" operator/universe_operator/main.py

# Expected: Event metadata includes fencing_token
```

**Pass Criteria**:
- ✅ `leader_election.py` docstring explicitly states "forensic markers"
- ✅ Docstring includes "What fencing tokens DO NOT do" section
- ✅ Event metadata includes fencing token in `meta` field

**Purpose**: During split-brain incident, event metadata allows post-mortem analysis:
- Which leadership epoch wrote which events
- Trace holder_identity and lease resourceVersion
- Correlate with Prometheus metrics for leader transitions

**If FAIL**: Review `operator/universe_operator/leader_election.py` docstring.

---

### 6. EventStoreError Alert + Runbook

**Objective**: Verify critical S3 write failure alert exists with runbook.

**Commands**:

```bash
# Check alert definition exists
grep "RynxsEventStoreErrorsHigh" docs/PROMETHEUS_ALERTS.md

# Expected: Alert definition with expr, for, labels, annotations

# Check runbook exists
grep -A50 "Runbook: RynxsEventStoreErrorsHigh" docs/PROMETHEUS_ALERTS.md

# Expected: Diagnosis steps and resolution matrix
```

**Pass Criteria**:
- ✅ Alert defined with `rate(rynxs_s3_put_errors_total[5m]) > 0.05`
- ✅ Runbook includes diagnosis steps
- ✅ Runbook includes resolution matrix for error types:
  - **AccessDenied**: IAM/bucket policy issue
  - **PreconditionFailed**: CAS conflict (split-brain or rogue writer)
  - **NoSuchBucket**: Bucket misconfiguration

**Operational Value**: These 3 error types drive different incident responses:
- `AccessDenied` → Check secret rotation, bucket policy principal ARN
- `PreconditionFailed` → Check leader election metrics, verify single leader
- `NoSuchBucket` → Verify bucket exists, check endpoint configuration

**If FAIL**: Add alert to `docs/PROMETHEUS_ALERTS.md`.

---

### 7. Rogue Writer Protection

**Objective**: Verify only authorized principals can write to S3 event log bucket.

**Commands**:

```bash
# List all IAM principals with s3:PutObject permission on bucket
# (Robust filter handles both string and array Action formats)
aws s3api get-bucket-policy --bucket rynxs-events-prod \
  | jq -r '.Policy | fromjson
    | .Statement[]
    | select((.Action|type)=="string" and .Action=="s3:PutObject"
          or (.Action|type)=="array" and (any(.Action[]; .=="s3:PutObject")))
    | .Principal'

# Expected: Only operator IAM role ARN
# Example: {"AWS": "arn:aws:iam::123456789012:role/rynxs-operator"}

# Check IAM role trust policy (who can assume this role)
aws iam get-role --role-name rynxs-operator \
  | jq '.Role.AssumeRolePolicyDocument.Statement[0].Principal'

# Expected: Only Kubernetes ServiceAccount (OIDC provider)
```

**Pass Criteria**:
- ✅ Bucket policy allows `s3:PutObject` for **single** principal (operator role)
- ✅ IAM role can only be assumed by operator ServiceAccount

**Risk**: Multiple writers (even with conditional writes) increase collision probability and complicate forensics.

**If FAIL**:
- Remove unnecessary IAM principals from bucket policy
- Review IAM role trust policy for overly permissive assumptions

---

## Post-Deployment Verification

Run these checks **after** `helm install/upgrade` completes.

### 8. Leader Election Status

```bash
# Verify exactly 1 leader elected
kubectl exec -n rynxs deployment/rynxs-operator -- \
  curl -s http://localhost:8080/metrics | grep rynxs_leader_election_status

# Expected: rynxs_leader_election_status{...} 1 (for exactly one pod)
# Sum across all pods should equal 1

# Check operator logs for leadership acquisition
kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs --tail=50 | grep -i "leader"

# Expected: One pod logs "Acquired leadership"
```

**Pass Criteria**:
- ✅ `sum(rynxs_leader_election_status) == 1`
- ✅ Exactly one pod logs leadership acquisition
- ✅ No `rynxs_leader_election_failures_total` increases

---

### 9. S3 Event Log Write Test

```bash
# Create test Agent CR to trigger event write
kubectl apply -f - <<EOF
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: test-prod-validation
  namespace: rynxs
spec:
  role: sandbox
  image: python:3.11-slim
EOF

# Wait for event to be written to S3
sleep 10

# Check S3 for new event files
aws s3 ls s3://rynxs-events-prod/events/ --recursive | tail -5

# Expected: New event files with sequential naming (0000000XXX.json)

# Verify event contains fencing token
aws s3api get-object \
  --bucket rynxs-events-prod \
  --key events/$(aws s3 ls s3://rynxs-events-prod/events/ | tail -1 | awk '{print $4}') \
  /dev/stdout | jq '.meta.fencing_token'

# Expected: Object with holder_identity, resource_version, epoch fields

# Cleanup test Agent
kubectl delete agent test-prod-validation -n rynxs
```

**Pass Criteria**:
- ✅ New event files appear in S3 bucket
- ✅ Event metadata includes `fencing_token` object
- ✅ No `AccessDenied` or `PreconditionFailed` errors in operator logs

---

### 10. Prometheus Alerts Active

```bash
# Check Prometheus has loaded rynxs alerts
kubectl exec -n monitoring prometheus-xxx -- \
  wget -q -O- http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name | contains("rynxs"))'

# Expected: Alert rules for:
# - RynxsNoLeader
# - RynxsLeaderFlap
# - RynxsLeaderElectionFailuresHigh
# - RynxsReplayDurationHigh
# - RynxsEventStoreErrorsHigh
```

**Pass Criteria**:
- ✅ All 5 critical alerts loaded in Prometheus
- ✅ No alerts firing (in healthy steady state)

---

## Ultra-Quick Smoke Test (4-Step)

**Purpose**: Final release gate - verify core functionality in <2 minutes.

```bash
# Step 1: Exactly 1 leader elected
kubectl exec -n rynxs deployment/rynxs-operator -- \
  curl -s http://localhost:8080/metrics | grep rynxs_leader_election_status | awk '{sum+=$2} END {print sum}'

# Expected: 1 (sum across all pods)

# Step 2: S3 has at least 2 events (initial state)
aws s3 ls s3://rynxs-events-prod/events/ | wc -l

# Expected: ≥2 (0000000000.json, 0000000001.json)

# Step 3: Conditional write enforcement works (2nd write fails)
KEY="events/smoke-test-$(date +%s).json"
aws s3api put-object --bucket rynxs-events-prod --key $KEY --body /dev/null --if-none-match '*'
aws s3api put-object --bucket rynxs-events-prod --key $KEY --body /dev/null --if-none-match '*'

# Expected: First write 200 OK, second write 412 PreconditionFailed

# Step 4: Pods distributed across zones (if multi-zone cluster)
kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs \
  -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' \
  | xargs -I {} kubectl get node {} -o jsonpath='{.metadata.labels.topology\.kubernetes\.io/zone}{"\n"}' \
  | sort -u | wc -l

# Expected: ≥2 (pods in at least 2 zones for replicaCount=3)
```

**Pass Criteria (All 4 must pass)**:
- ✅ Step 1: sum = 1 (single leader)
- ✅ Step 2: ≥2 event files in S3
- ✅ Step 3: Second conditional write returns 412
- ✅ Step 4: ≥2 unique zones (if multi-zone cluster)

**If any FAIL**: Review corresponding validation section above before proceeding.

---

## Final Sign-Off Criteria

**Production deployment is approved if**:
1. ✅ All 10 validation checks PASS
2. ✅ No firing alerts in Prometheus (after 10min stabilization)
3. ✅ Test Agent CR successfully triggered S3 event write
4. ✅ Exactly 1 leader elected and stable
5. ✅ Pods distributed across multiple zones (if multi-zone cluster)

**Controlled risks remaining**:
- Split-brain possible during network partition (mitigated by multi-layer guards + forensics)
- Leader election not absolute guarantee (mitigated by CAS in event store + cooldown)
- MinIO conditional write enforcement not guaranteed (use AWS S3 for production)

**Incident response readiness**:
- ✅ Runbooks documented for all critical alerts
- ✅ Fencing tokens enable post-mortem analysis
- ✅ Event log immutability enforced at S3 layer
- ✅ Observability metrics track leader status, transitions, and failures

---

## References

- [S3 Bucket Policy Documentation](S3_BUCKET_POLICY.md)
- [Prometheus Alerts + Runbooks](PROMETHEUS_ALERTS.md)
- [Leader Election Implementation](../operator/universe_operator/leader_election.py)
- [Production Values Example](../helm/rynxs/values-production.yaml)
