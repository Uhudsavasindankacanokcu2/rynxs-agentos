# Determinism Checklist

This checklist defines the non-determinism sources we must control and the approved patterns for handling them.

## Hard Rules
- **No I/O in decision layer**: decisions are pure (state, event) → actions.
- **No randomness**: no `random`, UUIDs, timestamps, or environment reads inside reducer/decision logic.
- **Stable ordering**: all lists/dicts that influence decisions must be sorted/canonicalized.
- **Side effects only in executor**: only executor touches K8s APIs or external systems.

## Common Non-Determinism Sources

### Time
- **Allowed**: deterministic clock (`engine/core/clock.py`) or event-provided timestamps.
- **Forbidden**: `time.time()`, `datetime.now()` in decision/reducer.

### Randomness / UUID
- **Allowed**: deterministic IDs from `engine/core/ids.py`.
- **Forbidden**: `uuid.uuid4()`, `random.*` for any decision or hash.

### Environment / Process State
- **Allowed**: env vars in **operator wiring** or executor.
- **Forbidden**: env vars in reducer/decision.

### External API Ordering
- **K8s list ordering**: must sort by stable keys (name/namespace).
- **Dict ordering**: always canonicalize before hashing or comparison.

### Server-Side Defaults
- **Rule**: adapter must normalize implicit defaults so semantically identical specs hash the same.

## Approved Patterns
- Canonical JSON via `engine/core/canonical.py`
- Action ordering via `decision_layer.actions_to_canonical`
- Append-only log with hash chain integrity
- Signed checkpoints and replay

## CI Gates
- `scripts/determinism_gate.sh` must pass
- Golden + weird fixtures must match expected state hash
- Pointer/proof verification must pass
