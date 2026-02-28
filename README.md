<p align="center">
  <img src="assets/official-banner.jpg" width="800" alt="Rynxs Official Banner">
</p>

# Rynxs — Governed AI Computers on Kubernetes

Rynxs is a Kubernetes-native platform for running **governed "AI computers"** — agents with real tools (workspace, shell, browser) but with **auditability, safety, and operational control**.

In the last release cycle we shipped: **one-command Helm deploy**, **HA leader election + failover**, **S3/MinIO append-only event log with hash-chain integrity**, and **production-grade observability** (Prometheus metrics, alerts, runbooks, structured JSON logs).

This isn't "magic guarantees" — it's **mitigated, observable, and forensically analyzable** reliability, aligned with distributed systems reality.

If your team needs agents to operate with real capabilities **without losing control**, Rynxs is built for that.

---

## Key Capabilities

- **One-command deployment** — Helm chart with production defaults, least-privilege RBAC, and documented lifecycle
- **High availability** — Multi-replica operator with Kubernetes Lease leader election and tested failover
- **Durable event log** — S3/MinIO append-only storage with hash-chain integrity and tamper detection
- **Policy enforcement** — Default-deny networking, sandboxed execution (gVisor/Kata support), immutable audit trail
- **Production observability** — Prometheus metrics, critical alerts with runbooks, structured JSON logs
- **Controlled risk posture** — Split-brain mitigations, forensic fencing tokens, and go-live checklists

---

## Branch Guide

- **main**: Full Kubernetes architecture (operator + sandbox + policy enforcement)
- **evo/deterministic-engine-v2**: Production hardening branch (HA + S3 + observability) — **SHIP READY**
- **proof-lite**: Minimal deterministic runtime (no external dependencies)
- **production-arch**: Enterprise sandbox development lane (gVisor/Kata, policy packs, signed images)

---

## Quick Start

### Production deployment (Helm)

```bash
# Install with default configuration
helm install rynxs ./helm/rynxs

# Production deployment with HA (recommended)
helm install rynxs ./helm/rynxs -n rynxs --create-namespace -f helm/rynxs/values-production.yaml

# Verify installation
kubectl get pods -n rynxs -l app.kubernetes.io/name=rynxs
kubectl logs -n rynxs -l app.kubernetes.io/name=rynxs
```

See `docs/PRODUCTION_CHECKLIST.md` for full go-live validation.

### Development quickstart (Kustomize)

```bash
# Install CRDs + operator
kubectl apply -f crds/
kubectl apply -k deploy/kustomize/base

# Create test agent
kubectl apply -f docs/examples/agent.yaml

# Watch operator logs
kubectl logs -f -l app=rynxs-operator
```

### Verify agent execution

```bash
# Find agent pod
POD=$(kubectl get pods -l app=universe-agent -o jsonpath='{.items[0].metadata.name}')

# Send task
kubectl exec $POD -- sh -c 'echo "{\"text\":\"run uname -a\"}" >> /workspace/inbox.jsonl'

# Check audit trail
kubectl exec $POD -- tail /workspace/audit.jsonl

# Verify sandbox job created
kubectl get jobs | grep sandbox-shell
```

---

## Production Readiness

Rynxs has been hardened and validated for **production deployment** with a focus on **HA, durability, observability, and controlled risk**.
This repo includes an operator Helm chart, S3-backed event log, leader election, alerts/runbooks, and a go-live checklist.

### What this proves (in plain terms)

- **Deployable**: single-command installs via Helm (no manual YAML orchestration).
- **HA (High Availability)**: multi-replica operator with Kubernetes Lease leader election + failover validation.
- **Durable state**: append-only event log in **S3/MinIO**, with hash-chain integrity checks.
- **Observable operations**: Prometheus metrics + critical alerts + runbooks for incident response.
- **Controlled risk posture**: no "magic guarantees"; split-brain is **mitigated** and **forensically analyzable**.

### Start here (Go-live)

- **Go-live gate / validation checklist:** `docs/PRODUCTION_CHECKLIST.md`
- **Alerts + runbooks:** `docs/PROMETHEUS_ALERTS.md`
- **S3 conditional write enforcement:** `docs/S3_BUCKET_POLICY.md`

### Timeline (how we got here)

- **Milestone changelog:** `docs/MILESTONE_CHANGELOG.md`
- **Exec summary:** `docs/EXECUTIVE_SUMMARY.md`
- **Release notes & sign-off:** `docs/RELEASE_NOTES.md`, `docs/RELEASE_SIGNOFF.md`

---

## Architecture

Rynxs uses a Kubernetes operator pattern with event-sourced state management:

**Control Plane**
- Operator watches `Agent` and `Universe` CRDs
- Event-sourced reconciliation with append-only log
- Leader election for HA (Kubernetes Lease)
- S3/MinIO durable storage with hash-chain integrity

**Execution Plane**
- Agent runtime with workspace + dual audit trail:
  - Workspace-level traces (`/workspace/audit.jsonl`)
  - S3-backed event log (hash-chained, for HA and forensic integrity)
- Sandboxed jobs for shell/browser execution
- Default-deny networking (NetworkPolicy)
- Optional gVisor/Kata runtime isolation

**Security Defaults**
- Non-root containers (`runAsNonRoot: true`)
- Read-only root filesystem
- No privilege escalation
- Minimal capabilities (`drop: ["ALL"]`)
- Pod Security Admission (baseline/restricted)

See `docs/MILESTONE_CHANGELOG.md` for detailed evolution timeline.

---

## Documentation

**Getting Started**
- `docs/PRODUCTION_CHECKLIST.md` - Go-live validation (10 steps + 2 min smoke test)
- `docs/MILESTONE_CHANGELOG.md` - Production readiness timeline (E1→E4→E2→E3→Hardening)
- `helm/rynxs/README.md` - Helm chart usage and configuration

**Operations**
- `docs/PROMETHEUS_ALERTS.md` - Alerts and runbooks
- `docs/S3_BUCKET_POLICY.md` - S3 conditional write enforcement
- `docs/RBAC.md` - RBAC permissions documentation

**Release**
- `docs/RELEASE_NOTES.md` - Public release notes
- `docs/RELEASE_SIGNOFF.md` - Internal ops sign-off
- `docs/EXECUTIVE_SUMMARY.md` - Technical executive overview

---

## Contributing

See `CONTRIBUTING.md` for development workflow and guidelines.

---

## License

Apache-2.0
