# Threat Model & Determinism Edge Cases

## Overview

This document catalogs threats to determinism and integrity, along with mitigations.

**Critical Rule**: Hataya yer yok. Every threat must have a concrete mitigation.

---

## Threats

### T1 - Log Tampering (Insider / Disk Access)

**Threat**: Attacker with disk access modifies event log to rewrite history.

**Attack Scenarios**:
- Insider deletes events to hide malicious activity
- Ransomware modifies log before encryption
- Compromised backup system alters historical logs

**Mitigation**:
- ✅ Hash chain: Each event chains to previous hash
- ✅ Checkpoint signatures: Signed snapshots at intervals
- ✅ Append-only storage: No updates, no deletes
- ✅ Verification tool: `engine verify` detects tampering

**Implementation**: `engine/log/integrity.py`

**Test Coverage**: `engine/tests/test_hash_chain.py::test_hash_chain_break_detection`

---

### T2 - Split-Brain / Concurrent Writers

**Threat**: Two writers append events simultaneously, causing sequence collision.

**Attack Scenarios**:
- Two operator replicas write to same log file
- Network partition causes dual leaders
- Crash recovery race condition

**Mitigation**:
- ✅ Single-writer lock (MVP): File lock + single writer process
- 🔄 Leader election (production): Raft/etcd for distributed systems
- 🔄 Atomic append strategy: Use database with ACID guarantees

**Implementation Notes**:
- MVP: `fcntl.flock()` on log file
- Production: Leader election via K8s lease mechanism

**Test Coverage**: TBD (M6 - distributed systems)

---

### T3 - Non-Deterministic Serialization

**Threat**: JSON key order / whitespace / unicode normalization differences.

**Attack Scenarios**:
- Python dict iteration order (pre-3.7 or set usage)
- Different JSON libraries produce different output
- Unicode NFC vs NFD normalization

**Mitigation**:
- ✅ Canonical JSON: `canonical_json_bytes()` enforces:
  - sort_keys=True
  - separators=(",", ":") (no whitespace)
  - ensure_ascii=False (UTF-8 stable)
- ✅ Canonicalize preprocessing: Sort dict keys recursively
- ⚠️ Unicode normalization: Policy required (see edge cases below)

**Implementation**: `engine/core/canonical.py`

**Test Coverage**: `engine/tests/test_canonical.py::test_canonical_json_bytes_determinism`

---

### T4 - Floating Point Non-Determinism

**Threat**: `0.1 + 0.2 != 0.3` across platforms/compilers.

**Attack Scenarios**:
- Replay on different CPU architecture (x86 vs ARM)
- Python version differences in float handling
- Compiler optimization changes float behavior

**Mitigation**:
- ✅ **Floats banned**: All numeric values are int or Decimal
- ✅ Fixed-point integers: Multiply by 10^n for decimal precision
- ✅ Decimal strings: Serialize as string, parse deterministically

**Policy**:
```python
# ❌ NEVER use float
payload = {"score": 0.95}  # FORBIDDEN

# ✅ Use fixed-point int
payload = {"score": 95}  # Represents 0.95 (multiply by 100)

# ✅ Or use Decimal as string
from decimal import Decimal
payload = {"score": str(Decimal("0.95"))}
```

**Implementation**: Code review + linter rule

**Test Coverage**: `engine/tests/test_determinism_policy.py::test_no_floats` (TBD)

---

### T5 - External Side Effects During Replay

**Threat**: Replay calls external APIs, writes files, sends notifications.

**Attack Scenarios**:
- Reducer calls Kubernetes API during replay
- Event handler sends email notification
- State transition writes to database

**Mitigation**:
- ✅ Pure reducers: Reducer functions are **pure** (no I/O, no side effects)
- ✅ Side effects in separate phase: Apply plan **after** replay
- ✅ Code review: Flag any I/O in reducer code

**Architecture**:
```
1. Replay (pure): events → state
2. Plan (pure): state → desired changes
3. Apply (impure): desired changes → actual effects
```

**Implementation**: `engine/core/reducer.py` (pure functions only)

**Test Coverage**: `engine/tests/test_reducer_pure.py::test_reducer_immutability`

---

### T6 - Time and Randomness

**Threat**: `datetime.now()`, `uuid.uuid4()`, `random.randint()` break determinism.

**Attack Scenarios**:
- Event timestamp from system clock
- UUID generation for aggregate IDs
- Random initialization of state

**Mitigation**:
- ✅ Deterministic clock: `DeterministicClock` (monotonic, no system time)
- ✅ Stable IDs: `stable_id(*parts)` (hash-based, no UUIDs)
- ✅ No randomness: Ban `random`, `uuid`, `time` modules in core

**Policy**:
```python
# ❌ NEVER use system time
ts = int(time.time())  # FORBIDDEN

# ✅ Use deterministic clock
clock = DeterministicClock(current=1000)
ts = clock.now()

# ❌ NEVER use UUID
id = str(uuid.uuid4())  # FORBIDDEN

# ✅ Use stable_id
id = stable_id("agent", "alpha", "1")
```

**Implementation**: `engine/core/clock.py`, `engine/core/ids.py`

**Test Coverage**: `engine/tests/test_clock.py::test_clock_determinism` (TBD)

---

### T7 - K8s API Non-Determinism

**Threat**: `list()` returns different order; server adds fields; resourceVersion changes.

**Attack Scenarios**:
- Pod list order changes between calls
- Server adds new field in API response
- ResourceVersion changes on every read

**Mitigation**:
- ✅ Normalize/strip ignored fields: Remove resourceVersion, managedFields
- ✅ Sort lists: Sort by name/uid before processing
- ✅ Compare by keys: Use canonical comparison

**Implementation**: `operator/universe_operator/k8s_normalize.py` (TBD)

**Policy**:
```python
# ❌ NEVER iterate K8s list directly
for pod in api.list_namespaced_pod(ns):
    process(pod)  # FORBIDDEN (order non-deterministic)

# ✅ Sort by name first
pods = sorted(api.list_namespaced_pod(ns), key=lambda p: p.metadata.name)
for pod in pods:
    process(pod)
```

**Test Coverage**: `operator/tests/test_k8s_determinism.py` (TBD)

---

## Determinism Edge Cases Checklist

### 1. Dict Key Ordering
- ✅ **Status**: Mitigated via `canonicalize()`
- **Test**: `test_canonical.py::test_canonicalize_dict_key_order`

### 2. List Ordering (Set Semantics)
- ⚠️ **Status**: Policy required
- **Policy**: If list has set semantics, sort by stable key
- **Test**: TBD

### 3. Unicode Normalization (NFC/NFKC)
- ⚠️ **Status**: Policy required
- **Policy**: All strings normalized to NFC before hashing
- **Implementation**: TBD (M6)

### 4. YAML Parsing Differences
- ⚠️ **Status**: Policy required
- **Policy**: YAML → JSON conversion must be deterministic
- **Mitigation**: Use `ruamel.yaml` with stable ordering

### 5. Python Hash Randomization
- ✅ **Status**: Mitigated via canonical serialization
- **Note**: Never rely on `hash()` for determinism, use SHA-256

### 6. Dependency Versions
- ⚠️ **Status**: Lock file required
- **Policy**: `pyproject.toml` + lock file (Poetry/uv)
- **Implementation**: TBD

### 7. OS Newline Differences
- ✅ **Status**: Mitigated via JSONL format
- **Policy**: Always use `\n` (Unix newline), no `\r\n`

### 8. Crash Safety
- ✅ **Status**: Fsync after append
- **Test**: `test_file_store.py::test_crash_recovery` (TBD)

### 9. Partial Line Detection
- ⚠️ **Status**: Verify tool required
- **Implementation**: `engine verify` checks for incomplete lines

---

## Verification Checklist

Before production deployment, verify:

- [ ] Replay determinism: 100 runs, identical state hash
- [ ] Hash chain integrity: Tamper detection works
- [ ] No floats in codebase: `grep -r "float(" engine/core/`
- [ ] No system time: `grep -r "time.time()" engine/core/`
- [ ] No UUIDs: `grep -r "uuid." engine/core/`
- [ ] No randomness: `grep -r "random." engine/core/`
- [ ] Canonical everywhere: All hashes use `canonical_json_bytes()`
- [ ] Pure reducers: No I/O in `engine/core/reducer.py`
- [ ] Fsync on append: `os.fsync()` called after write
- [ ] Lock file: `pyproject.toml` + locked dependencies

---

## Testing Strategy

### Unit Tests (M1-M5)
- Canonical serialization determinism
- Reducer purity (no mutations)
- Replay determinism (100 runs)
- Hash chain integrity (tamper detection)

### Property Tests (M6)
- Hypothesis: Generate random event streams
- Verify: Same events → same state (always)
- Verify: Tampering → detection (always)

### Chaos Tests (M7)
- Crash during append: Verify recovery
- Split-brain: Verify rejection
- Concurrent writers: Verify lock

### Formal Verification (M8)
- TLA+ model of core
- Prove determinism property
- Prove integrity property

---

## Incident Response

If determinism violation detected:

1. **Isolate**: Stop all writes to affected log
2. **Verify**: Run `engine verify` to find break point
3. **Analyze**: Examine events around break point
4. **Restore**: Replay from last valid checkpoint
5. **Root cause**: Identify policy violation
6. **Patch**: Fix code, add test, deploy

**Critical**: Never ignore determinism violation. It indicates a fundamental failure.

---

## Responsible Disclosure

If you discover a determinism or integrity vulnerability:

1. Email: security@rynxs.ai (PGP key in repo)
2. Do not disclose publicly until patched
3. We will credit you in release notes

---

## Compliance Mapping

This threat model satisfies:

- **SOC 2 Type II**: Audit trail integrity
- **ISO 27001**: Cryptographic controls
- **NIST 800-53**: Audit and accountability
- **GDPR**: Right to explanation (via replay)
- **HIPAA**: Audit log requirements

---

## Revision History

- 2026-02-25: Initial version (T1-T7, edge cases checklist)
