# Rynxs Evolution Strategy

## Branch Structure

### main
Stable releases and hotfixes only.

### evo/revenue-enterprise-v1
**Goal:** $10K MRR in 6 months  
**Definition of Done:** 1 komutla cluster'a kurulur + policy/audit hazır + demo müşteri akışı var.

**Focus:**
- Multi-tenant / namespace-per-tenant
- RBAC hardening + least privilege
- Audit logging (immutable format)
- Helm production defaults (HA, resources, probes)
- Policy packs (egress control, runtime class)
- Documentation: quickstart + security posture

**Target:** Enterprise customers (fintech, gov, regulated industries)

---

### evo/deterministic-engine-v2 ⭐ PRIMARY FOCUS
**Goal:** Deterministic execution engine = replayable, verifiable, audit-ready AI workloads  
**Definition of Done:** Replay + hash-chain ile 'kanıtlanabilir' execution var; operator buna bağlanıyor.

**Focus:**
- Event-sourcing core (append-only)
- Deterministic state transitions (pure functions)
- Hash-chain / signed checkpoints
- Replay tool (same input → same output)
- Operator controllers transition to engine-driven reconcile

**Impact:** This is the paradigm shift. World-changing tech.

---

### evo/cognitive-runtime-v3
**Goal:** Research track - K8s-level cognitive scheduler/runtime  
**Definition of Done:** Scheduler PoC, cost/risk placement kararını ölçülebilir şekilde veriyor.

**Focus:**
- "Cognition cost" scheduler prototype
- Risk-based isolation policy (dynamic sandbox)
- Workload placement: trust/latency/cost scoring
- K8s-independent PoC (later K8s plugin)

**Type:** Research + prototype. Not merged to main.

---

## Merge Strategy

- **main ← revenue-enterprise-v1:** Full merge when stable
- **deterministic-engine-v2 → revenue-enterprise-v1:** Cherry-pick selected features
- **cognitive-runtime-v3:** No merge. Results = papers/blogs/prototypes

---

## Timeline

**Month 1-2:** deterministic-engine-v2 core  
**Month 2-4:** revenue-enterprise-v1 productization  
**Month 3-6:** cognitive-runtime-v3 research (parallel)  
**Month 6:** $10K MRR target + deterministic engine production-ready
