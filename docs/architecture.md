# Architecture Refinement: World-Changing Deterministic Engine

## Vision

Current architecture: Event-sourced deterministic core.

This document refines the architecture from "interesting K8s operator" to "paradigm-shifting governable AI infrastructure".

## Three-Layer Architecture

### Layer 1: Deterministic Kernel (K8s-independent)

**Guarantee**: "Same event stream → same state hash"

**Core Principles**:
- Canonicalization policy: JSON canonical + stable ordering + type normalization
- No floats: All numbers are int (fixed-point) or Decimal (string serialize)
- Deterministic clock: ts only comes from event producer
- Deterministic IDs: stable_id() or content-addressed IDs
- Deterministic side effects: No side effects; only produce events

**Why This Matters**:
This kernel can be **formalized** and **proven correct**. Academic papers can be written about this.
It's not "yet another event sourcing library" - it's a **verified deterministic computation engine**.

**Key Components**:
- `engine/core/canonical.py` - Canonical serialization (heart of determinism)
- `engine/core/reducer.py` - Pure state transitions
- `engine/core/events.py` - Immutable event model
- `engine/log/integrity.py` - Hash chain verification

**Formal Properties**:
1. **Determinism**: ∀ events e₁...eₙ, replay(e₁...eₙ) = replay(e₁...eₙ)
2. **Integrity**: tamper(log) → verify(log) = false
3. **Replayability**: state(t) = reduce(∅, events[0:t])

### Layer 2: Policy/Verification Layer (Guardians)

**Amaç**: "Policy-enforced AI" - enterprise bread and butter

**Core Principles**:
- Admission-style validation but K8s-independent:
  ```python
  validate(event, current_state) -> allow/deny + reason
  ```
- Policy as code: Rego (OPA) or custom DSL
- Deterministic audit: Every deny/allow decision logged as event (full trail)
- Replayable compliance: Auditor gets same verdict from same log

**Example Policies**:
```python
# Policy 1: Agent resource limits
def validate_agent_created(event, state):
    if event.payload["cpu"] > 4:
        return deny("CPU limit exceeded")
    return allow()

# Policy 2: Task assignment rules
def validate_task_assigned(event, state):
    agent = state.get_agg(event.payload["agent_id"])
    if agent["active_tasks"] >= 10:
        return deny("Agent task limit exceeded")
    return allow()

# Policy 3: Audit trail requirement
def validate_task_completed(event, state):
    if "audit_log" not in event.meta:
        return deny("Audit log required for task completion")
    return allow()
```

**Why This Matters**:
- Compliance teams can **verify** that policies were enforced
- Security teams can **replay** incidents to understand what happened
- Auditors can **prove** that no policy violations occurred

**Implementation Path**:
- M6: Policy engine core
- M7: OPA integration
- M8: Policy audit dashboard

### Layer 3: Runtime Integration Layer (K8s Operator / CRDs)

**Amaç**: Connect kernel to real cluster

**Core Principles**:
- Operator is just event producer/consumer:
  - CRD update → event append
  - reconcile → store read + replay → desired manifests
- Controller side effects:
  - Kernel state → plan
  - Apply plan
  - Log "plan applied" event
- K8s non-determinism isolation:
  - API list ordering, resourceVersion, timestamps = meta "ignored field list"

**Critical Rule**: Everything operator does must be **explainable** by deterministic core.

**Example Flow**:
```
1. User creates Agent CRD
2. Operator watches CRD → produces "AgentCreated" event
3. Event appended to log (hash chain)
4. Replay produces desired state
5. Operator applies manifests (Pod, PVC, etc.)
6. Operator logs "AgentManifestsApplied" event
7. Reconcile loop continues...
```

**K8s Non-Determinism Handling**:
- List results: Sort by name before processing
- ResourceVersion: Store in meta, exclude from hash
- Server timestamps: Use deterministic clock for event ts
- UID fields: Generate deterministic IDs where possible

## Branch Integration

### evo/revenue-enterprise-v1 (6-month revenue path)
- Focus: Policy + Audit + Compliance UI
- Uses Layer 2 + Layer 3
- Target: Enterprise customers (fintech, gov, regulated)

### evo/deterministic-engine-v2 (PRIMARY - paradigm shift)
- Focus: Layer 1 (Kernel) + replay + hash chain + checkpoint
- This is the **academic contribution**
- This is what makes us **world-changing**

### evo/cognitive-runtime-v3 (research track)
- Focus: Scheduling/risk/cognition cost
- Built on top of Layer 1
- Future: AI-native scheduler

## Implementation Priorities

**Month 1-2**: Layer 1 (Deterministic Kernel)
- M1: Core abstractions
- M2: EventStore
- M3: Hash chain
- M4: Checkpoints
- M5: Replay

**Month 2-3**: Layer 3 (K8s Integration)
- Operator dual-write (current + events)
- Replay verification
- Full deterministic reconcile

**Month 3-6**: Layer 2 (Policy Engine)
- Policy validation framework
- OPA integration
- Audit dashboard
- Compliance reports

## Success Metrics

**Layer 1 (Technical)**:
- 100 replays, 0 state divergence
- Hash chain integrity: 100% tamper detection
- Performance: 10,000 events/sec

**Layer 2 (Product)**:
- Policy violation detection: <100ms
- Audit log completeness: 100%
- Compliance report generation: <1min for 1M events

**Layer 3 (Production)**:
- Operator reconcile: deterministic state match 100%
- CRD → event latency: <10ms
- Replay recovery time: <30s for 100K events

## Formal Verification Roadmap

**Phase 1: Model Checking** (Month 4)
- TLA+ model of reducer
- Verify determinism property
- Verify integrity property

**Phase 2: Property Testing** (Month 5)
- Hypothesis/QuickCheck tests
- Generate random event streams
- Verify state convergence

**Phase 3: Academic Paper** (Month 6)
- "Deterministic Execution Engine for Governable AI"
- Submit to OSDI/SOSP/NSDI
- Open source release

## Why This Is World-Changing

Current AI systems: **Black boxes**
- Can't explain decisions
- Can't replay history
- Can't verify compliance
- Can't audit behavior

Our system: **Glass boxes**
- Every decision recorded
- Full history replay
- Cryptographic verification
- Complete audit trail

**This enables AI in regulated industries for the first time.**

Finance, healthcare, government - these industries need AI but can't accept black-box risk.

We give them:
- Auditability
- Reproducibility
- Accountability
- Trust

This is not "AI + Kubernetes".
This is **provable AI governance**.

That's the paradigm shift.
