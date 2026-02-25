# Deterministic Engine Milestones

## Overview

This document tracks the implementation of the deterministic execution engine - the paradigm shift that makes AI workloads replayable, verifiable, and audit-ready.

## Repo Structure

```
/engine
  /core       # Event types, State model, Reducers, Clock, Deterministic IDs
  /log        # EventStore interface, file_store, sqlite_store, integrity checks
  /checkpoint # Checkpoint model, signer, verifier, snapshot utilities
  /replay     # Replay runner, diff utilities, trace output
  /cli        # CLI commands (init, append, replay, verify, checkpoint)
  /tests      # Unit tests for all components
```

---

## Milestone 1: Deterministic Core

**Goal**: Pure functional core with Event + State + Reducer pattern

**Files to Create**:
- `engine/core/event.py` - Event dataclass with type, aggregate_id, seq, timestamp, payload, metadata
- `engine/core/state.py` - State dataclass with version and aggregates dict
- `engine/core/reducer.py` - Pure reducer function: `(state: State, event: Event) -> State`
- `engine/core/clock.py` - Deterministic clock (monotonic, no system time dependency)
- `engine/core/id_gen.py` - Deterministic ID generator (sequence-based, collision-free)
- `engine/tests/test_reducer.py` - Test reducer purity and determinism

**Acceptance Criteria**:
- [ ] Event model supports arbitrary JSON payloads
- [ ] State model tracks multiple aggregates (agents, tasks, teams)
- [ ] Reducer is pure: same (state, event) always produces same output
- [ ] Clock is monotonic and deterministic (no `time.time()` calls)
- [ ] ID generator produces collision-free IDs from sequence numbers
- [ ] Tests verify: same input → same output (run 100x)

**CLI Commands** (to be implemented in M2+):
```bash
# Not applicable for M1 - core interfaces only
```

---

## Milestone 2: Append-Only EventStore

**Goal**: Persistent event log with file-based backend

**Files to Create**:
- `engine/log/event_store.py` - EventStore interface (append, read, get_since_seq)
- `engine/log/file_store.py` - File-based implementation (JSONL format)
- `engine/log/sqlite_store.py` - SQLite implementation (for future scalability)
- `engine/tests/test_event_store.py` - Test append, read, idempotency

**Acceptance Criteria**:
- [ ] EventStore interface defines: append(event), read_all(), get_since_seq(seq)
- [ ] File backend stores events as newline-delimited JSON
- [ ] Append operations are idempotent (duplicate seq rejected)
- [ ] Read operations return events in sequence order
- [ ] No mutations to existing entries (append-only guarantee)
- [ ] Tests verify: append 1000 events, read all, verify order

**CLI Commands**:
```bash
engine init --log-path ./logs/universe.log
engine append --type AgentCreated --aggregate-id agent-1 --payload '{"name":"alpha"}'
engine read --from-seq 0
```

---

## Milestone 3: Hash-Chain Integrity

**Goal**: Tamper-evident logging with cryptographic hash chains

**Files to Create**:
- `engine/log/integrity.py` - Hash chain functions (compute_event_hash, verify_chain)
- `engine/core/event.py` - Add `prev_hash` field to Event model
- `engine/log/file_store.py` - Update to compute and store prev_hash
- `engine/tests/test_integrity.py` - Test hash chain verification, tamper detection

**Acceptance Criteria**:
- [ ] Each event includes prev_hash (SHA-256 of previous event)
- [ ] Hash input: canonical JSON (sorted keys, no whitespace)
- [ ] Genesis event has prev_hash = "0" * 64
- [ ] verify_chain() detects any tampering (modified payload, reordered events)
- [ ] Tests verify: tamper detection (modify seq 50, verify fails at seq 51)

**CLI Commands**:
```bash
engine verify --log-path ./logs/universe.log
# Output:
# Hash chain valid: 0 -> 1234 (1235 events)
# Integrity: OK
```

---

## Milestone 4: Checkpoint System

**Goal**: Signed state snapshots for fast replay and audit trails

**Files to Create**:
- `engine/checkpoint/model.py` - Checkpoint dataclass (checkpoint_id, at_seq, state_hash, log_hash, signature, timestamp)
- `engine/checkpoint/signer.py` - Sign checkpoint with Ed25519 keypair
- `engine/checkpoint/verify.py` - Verify checkpoint signature and hashes
- `engine/checkpoint/snapshot.py` - Create checkpoint from state + log hash
- `engine/tests/test_checkpoint.py` - Test checkpoint creation, signing, verification

**Acceptance Criteria**:
- [ ] Checkpoint captures: state_hash (SHA-256 of state), log_hash (hash of event at at_seq), signature
- [ ] Signer uses Ed25519 keypair (generate, load from file)
- [ ] Verification checks: signature valid, state_hash matches replayed state, log_hash matches event
- [ ] Checkpoints stored as JSON files with .checkpoint extension
- [ ] Tests verify: create checkpoint at seq 100, replay to 100, verify hashes match

**CLI Commands**:
```bash
engine checkpoint create --at-seq 1000 --key-path ./keys/operator.key --output ./checkpoints/
# Output: checkpoints/checkpoint-1000-20260225T120000.checkpoint

engine checkpoint verify --checkpoint-path ./checkpoints/checkpoint-1000.checkpoint --log-path ./logs/universe.log
# Output:
# Checkpoint ID: checkpoint-1000-20260225T120000
# At sequence: 1000
# State hash: abc123...
# Log hash: def456...
# Signature: VALID
# Replay verification: PASSED
```

---

## Milestone 5: Replay System

**Goal**: Reproduce exact state from event log with tracing and diff utilities

**Files to Create**:
- `engine/replay/runner.py` - replay(log, until_seq) -> State
- `engine/replay/trace.py` - Trace output (event-by-event state transitions)
- `engine/replay/diff.py` - Diff two states (show what changed)
- `engine/tests/test_replay.py` - Test deterministic replay, trace output, diff accuracy

**Acceptance Criteria**:
- [ ] replay() applies reducer to each event in sequence order
- [ ] Replay from seq 0 to seq N produces identical state (run 100x)
- [ ] Trace mode outputs: seq, event type, aggregate_id, state diff
- [ ] Diff utility shows field-level changes between two states
- [ ] Tests verify: replay to seq 500, checkpoint, replay again, states match

**CLI Commands**:
```bash
engine replay --log-path ./logs/universe.log --until-seq 1000
# Output:
# Replayed 1000 events
# Final state: 45 agents, 120 tasks, 8 teams
# State hash: abc123...

engine replay --log-path ./logs/universe.log --trace --until-seq 10
# Output:
# [0] AgentCreated agent-1 | agents: {} -> {"agent-1": {...}}
# [1] TaskAssigned task-1 | tasks: {} -> {"task-1": {...}}
# ...

engine replay --log-path ./logs/universe.log --until-seq 1000 --diff-with ./checkpoints/checkpoint-1000.checkpoint
# Output:
# State diff: MATCH (no differences)
# Deterministic replay: VERIFIED
```

---

## Dependencies

```
M1 (Core) → M2 (EventStore) → M3 (Integrity) → M4 (Checkpoint)
                                                      ↓
                                                    M5 (Replay)
```

- M2 depends on M1 (needs Event and State models)
- M3 depends on M2 (adds hash chain to EventStore)
- M4 depends on M3 (checkpoints reference log hashes)
- M5 depends on M1, M2, M3 (replays events with integrity verification)

---

## Timeline

**Month 1**:
- Week 1-2: M1 + M2 (Core + EventStore)
- Week 3: M3 (Integrity)
- Week 4: M4 (Checkpoint)

**Month 2**:
- Week 1: M5 (Replay)
- Week 2-4: Operator integration Phase 1 (dual-write)

---

## Operator Integration Strategy

### Phase 1: Dual-Write (Month 2)
- Controller writes to both: K8s CRD status + event log
- No reads from event log yet
- Goal: Build event history without affecting current behavior

### Phase 2: Read from Engine (Month 3)
- Controller reads state from engine (via replay)
- K8s status becomes derived from event log
- Goal: Verify deterministic state matches K8s state

### Phase 3: Full Deterministic Control Plane (Month 4)
- All reconcile logic driven by engine
- K8s CRDs become input events only
- Goal: Replayable operator with audit trail

---

## Success Metrics

- [ ] Replay determinism: 100 runs, 0 state divergence
- [ ] Hash chain integrity: tamper detection 100% accurate
- [ ] Checkpoint verification: replay to checkpoint seq, hashes match
- [ ] Performance: 10,000 events/sec append rate
- [ ] CLI usability: 5-command interface (init, append, read, verify, checkpoint, replay)

---

## World-Changing Impact

This is not "Kubernetes + AI". This is:

**Provable AI Governance**

Every action, every decision, every state transition is:
- Recorded (append-only log)
- Verifiable (hash chain)
- Replayable (deterministic reducer)
- Auditable (signed checkpoints)

No AI system in production today can make these guarantees. This changes everything for regulated industries (finance, healthcare, government) that need AI but cannot accept black-box risk.
