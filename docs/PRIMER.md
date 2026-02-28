# Rynxs Primer — Understanding the System from Zero

This document explains Rynxs from first principles: what it is, why it works this way, and what each technical choice solves.

---

## What is Rynxs?

**The problem:**
AI agents need "computer capabilities" (shell access, file system, browser, tools) to be useful. But giving unrestricted access to these capabilities is dangerous:
- Agents can corrupt data
- Agents can leak sensitive information
- Agents can consume unlimited resources
- Multiple agents can conflict with each other

**Rynxs's solution:**
A Kubernetes-native platform that gives agents **governed computer capabilities**:
- Agents get workspaces, tools, and execution environments
- Every action is recorded in an immutable audit log
- Policies enforce isolation and resource limits
- Operations teams can observe, debug, and control the system

**In one sentence:**
Rynxs = "AI computers" with governance, auditability, and operational safety.

---

## Core Concepts (Zero to Understanding)

### 1. What is a Kubernetes Operator?

**Traditional approach:**
You write YAML files describing what you want (Deployments, Services, etc.) and manually apply them with `kubectl apply`.

**Problem:**
Complex systems need continuous reconciliation:
- "If agent wants GPU, provision GPU node"
- "If agent violates policy, terminate sandbox"
- "If leader pod dies, elect new leader"

**Operator pattern:**
A program running inside Kubernetes that:
1. Watches for custom resources (like `Agent` or `Universe`)
2. Compares desired state (what you declared) vs actual state (what exists)
3. Takes actions to reconcile the difference

**Example:**
```yaml
apiVersion: universe.ai/v1alpha1
kind: Agent
metadata:
  name: my-agent
spec:
  role: sandbox
  image: python:3.11-slim
```

The operator sees this and automatically creates:
- Deployment (agent pod)
- PVC (workspace storage)
- NetworkPolicy (isolation)
- ConfigMap (configuration)

**Why Rynxs uses operators:**
Because agent lifecycle is complex — you don't want to manually manage pods, storage, policies, and cleanup. The operator does it for you.

---

### 2. What is Event Sourcing?

**Traditional state management:**
Store current state in a database. When something changes, update the record.

**Problem:**
- You lose history (can't replay "how did we get here?")
- Debugging is hard (can't reproduce bugs)
- Audit trails are incomplete

**Event sourcing:**
Instead of storing current state, store **every event that happened** in an append-only log.

**Example:**
Traditional:
```
agents_table: { id: 1, status: "running", image: "python:3.11" }
```

Event sourcing:
```
events.log:
0000000001.json: {"type": "AgentCreated", "id": 1, "image": "python:3.11"}
0000000002.json: {"type": "AgentStarted", "id": 1, "timestamp": "2026-02-28T10:00:00Z"}
0000000003.json: {"type": "TaskAssigned", "id": 1, "task": "run tests"}
```

**Benefits:**
- **Auditability:** Full history of what happened
- **Reproducibility:** Replay events to reconstruct state
- **Debugging:** See exact sequence of events that led to a bug

**Why Rynxs uses event sourcing:**
Because AI agent behavior must be auditable and reproducible. Regulators, security teams, and developers need to know "what did the agent do?"

---

### 3. What is Hash-Chain Integrity?

**Problem:**
If someone tampers with your event log (deletes events, modifies events, reorders events), how do you detect it?

**Hash-chain solution:**
Each event includes:
1. `event_hash`: Hash of this event's content
2. `prev_hash`: Hash of the previous event

**Example:**
```
Event 1: { "data": "...", "event_hash": "abc123", "prev_hash": null }
Event 2: { "data": "...", "event_hash": "def456", "prev_hash": "abc123" }
Event 3: { "data": "...", "event_hash": "ghi789", "prev_hash": "def456" }
```

**Tamper detection:**
If someone modifies Event 2, its `event_hash` changes. But Event 3's `prev_hash` still points to the old hash → **chain is broken**.

**Why Rynxs uses hash-chains:**
Because append-only logs need **tamper evidence**. If an event is modified or deleted, the chain breaks and you know immediately.

---

### 4. What is Leader Election and Why Do We Need It?

**The HA problem:**
You want 3 replicas of the operator for high availability. But if all 3 replicas try to reconcile agents simultaneously, they'll conflict:
- Two replicas create the same Deployment → duplicate resources
- Two replicas write to the same event log → corrupted sequence numbers

**Solution: Leader election**
Only **one replica** (the leader) performs reconciliation. The other replicas wait.

**How it works (Kubernetes Lease):**
1. Operator tries to acquire a Lease object
2. First one to acquire it becomes leader
3. Leader renews the lease every N seconds
4. If leader dies, lease expires → another replica becomes leader

**Example:**
```
Replica A: "I own the lease, I'm the leader" (reconciles agents)
Replica B: "Lease is held by A, I'm a follower" (does nothing)
Replica C: "Lease is held by A, I'm a follower" (does nothing)

[Replica A crashes]

Replica B: "Lease expired, I'll take it, I'm the leader now" (takes over reconciliation)
```

**Why Rynxs uses leader election:**
Because without it, multi-replica deployments would create chaos. Leader election ensures **single-writer** behavior.

---

### 5. What is High Availability (HA)?

**HA goal:**
System stays operational even when components fail.

**Without HA:**
- Single operator pod → if it crashes, no reconciliation happens until restart
- Pod runs on Node 1 → if Node 1 dies, pod is lost

**With HA:**
- 3 operator replicas across 3 nodes → if one node dies, others continue
- Leader election ensures smooth failover

**Rynxs HA design:**
- Multi-replica operator (3+)
- Leader election (Kubernetes Lease)
- Shared durable log (S3/MinIO) so new leader can resume from where old leader left off
- PodDisruptionBudget (prevents all replicas from being evicted during node drain)
- Topology spread (distributes replicas across zones for zone-level failures)

**Why HA matters:**
Production systems can't tolerate single points of failure. HA keeps Rynxs running during upgrades, node failures, and zone outages.

---

## Why Rynxs Architecture is Built This Way

### Problem 1: "How do we audit agent behavior?"
**Solution:** Event sourcing + hash-chain → Every action is logged and tamper-evident.

### Problem 2: "How do we run multiple operator replicas without conflicts?"
**Solution:** Leader election + shared S3 log → Only leader writes, log is durable.

### Problem 3: "How do we recover from failures?"
**Solution:** HA + failover + deterministic replay → New leader replays events and continues.

### Problem 4: "How do we debug production issues?"
**Solution:** Structured logs + Prometheus metrics + alerts/runbooks → Observable system.

### Problem 5: "How do we prevent split-brain (two leaders writing simultaneously)?"
**Solution:** Multi-layer mitigations:
- Pre-apply leadership check
- Post-apply leadership check
- S3 conditional writes (If-None-Match)
- Leader loss cooldown
- Forensic fencing tokens

---

## Risk Posture: Why "Controlled and Observable"?

**Can Rynxs guarantee 100% no split-brain?**
No. Distributed systems physics apply:
- Network partitions can separate leader from API server
- Clock skew can cause lease expiration edge cases
- Kubernetes API can have transient failures

**What Rynxs does instead:**
1. **Mitigate:** Multi-layer guardrails reduce probability of split-brain
2. **Observe:** Metrics + alerts detect when problems happen
3. **Forensics:** Fencing tokens + event metadata allow post-mortem analysis

**This is honest engineering:**
We don't claim "magic guarantees." We claim "controlled and observable risk."

---

## Key Takeaways

1. **Rynxs = Governed AI computers** (agents with capabilities, but under control)
2. **Operator pattern** = Kubernetes watches your custom resources and reconciles state
3. **Event sourcing** = Append-only log of everything that happened (auditability + reproducibility)
4. **Hash-chain** = Tamper-evident integrity (detect if someone modifies the log)
5. **Leader election** = Only one replica reconciles at a time (prevents conflicts)
6. **HA** = Multiple replicas + failover + shared durable storage (survives failures)
7. **Risk posture** = Mitigated + observable + forensically analyzable (not magic, but honest)

---

## Where to Go Next

**If you want to deploy:**
- Start with `docs/PRODUCTION_CHECKLIST.md`
- Review `docs/MILESTONE_CHANGELOG.md` to understand evolution

**If you want to understand the code:**
- Read `operator/universe_operator/main.py` (operator entry point)
- Read `engine/log/s3_store.py` (event sourcing implementation)
- Read `operator/universe_operator/leader_election.py` (HA logic)

**If you want to operate:**
- Review `docs/PROMETHEUS_ALERTS.md` (alerts + runbooks)
- Review `docs/S3_BUCKET_POLICY.md` (S3 enforcement)
- Review `helm/rynxs/values-production.yaml` (production config)
