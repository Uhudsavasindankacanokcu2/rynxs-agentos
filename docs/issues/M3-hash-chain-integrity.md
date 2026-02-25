# M3: Hash-Chain Integrity

## Goal

Implement tamper-evident logging with cryptographic hash chains. Every event includes the hash of the previous event, forming an immutable chain. Any tampering (modification, deletion, reordering) breaks the chain and is immediately detectable.

## Description

Add cryptographic integrity to the event log:
- Each event includes `prev_hash` field (SHA-256 of previous event)
- Genesis event (seq=0) has `prev_hash = "0" * 64`
- Hash input uses canonical JSON (sorted keys, no whitespace) for determinism
- Verification walks the chain and detects any breaks

This makes the log tamper-evident: you cannot modify past events without breaking the hash chain.

## Files to Create

- `engine/log/integrity.py` - Hash chain functions
- `engine/core/event.py` - Add `prev_hash` field (modify existing)
- `engine/log/file_store.py` - Update to compute and store prev_hash (modify existing)
- `engine/tests/test_integrity.py` - Integrity verification tests

## Files to Modify

- `engine/core/event.py` - Add `prev_hash: str` field
- `engine/log/file_store.py` - Compute prev_hash on append

## Acceptance Criteria

- [ ] Event model includes `prev_hash: str` field
- [ ] Genesis event (seq=0) has prev_hash = "0" * 64 (64 zeros)
- [ ] Hash computation uses canonical JSON (sorted keys, compact format)
- [ ] Hash function: SHA-256 of canonical JSON
- [ ] FileStore computes prev_hash automatically on append
- [ ] `verify_chain(events: list[Event]) -> bool` walks chain and verifies each link
- [ ] `verify_chain` detects: modified payload, modified metadata, reordered events, deleted events, inserted events
- [ ] Tests verify: tamper detection works (modify event 50, verify fails at event 51)
- [ ] Tests verify: valid chain passes verification (1000 events, no tampering)

## Test Requirements

Create `test_integrity.py` with tests for:

1. **Valid Chain**: Append 100 events, verify chain, expect success
2. **Tamper Detection - Modified Payload**: Modify event 50 payload, verify chain, expect failure at event 51
3. **Tamper Detection - Reordered Events**: Swap events 50 and 51, verify chain, expect failure
4. **Tamper Detection - Deleted Event**: Delete event 50, verify chain, expect failure
5. **Tamper Detection - Inserted Event**: Insert duplicate event, verify chain, expect failure
6. **Genesis Event**: Verify event 0 has prev_hash = "0" * 64
7. **Canonical Hash**: Verify same event produces same hash regardless of dict key order

```python
def test_tamper_detection_modified_payload():
    """Modifying event payload should break hash chain."""
    store = FileStore(path="./test.log")

    # Append 100 events
    for i in range(100):
        event = create_test_event(seq=i, payload={"value": i})
        store.append(event)

    # Read and tamper with event 50
    events = store.read_all()
    events[50].payload["value"] = 999  # TAMPER

    # Verify chain - should fail at event 51
    result = verify_chain(events)
    assert result.valid == False
    assert result.broken_at_seq == 51
    assert "hash mismatch" in result.error.lower()
```

## Implementation Notes

**Update Event Model**:
```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Event:
    type: str
    aggregate_id: str
    seq: int
    timestamp: int
    payload: dict[str, Any]
    metadata: dict[str, Any]
    prev_hash: str  # NEW: SHA-256 hash of previous event
```

**Hash Chain Functions**:
```python
import hashlib
import json

def compute_event_hash(event: Event) -> str:
    """
    Compute SHA-256 hash of event using canonical JSON.

    Canonical JSON rules:
    - Keys sorted alphabetically
    - No whitespace
    - Consistent encoding (UTF-8)

    Returns 64-character hex string.
    """
    # Create dict without prev_hash (we're computing the hash of content)
    event_data = {
        "type": event.type,
        "aggregate_id": event.aggregate_id,
        "seq": event.seq,
        "timestamp": event.timestamp,
        "payload": event.payload,
        "metadata": event.metadata,
    }

    # Canonical JSON: sorted keys, no whitespace
    canonical = json.dumps(event_data, sort_keys=True, separators=(',', ':'))

    # SHA-256 hash
    hash_bytes = hashlib.sha256(canonical.encode('utf-8')).digest()
    return hash_bytes.hex()

def verify_chain(events: list[Event]) -> VerificationResult:
    """
    Verify hash chain integrity.

    Returns VerificationResult with:
    - valid: bool
    - broken_at_seq: int | None (first event where chain breaks)
    - error: str | None
    """
    if not events:
        return VerificationResult(valid=True)

    # Check genesis event
    if events[0].prev_hash != "0" * 64:
        return VerificationResult(
            valid=False,
            broken_at_seq=0,
            error="Genesis event prev_hash must be 64 zeros"
        )

    # Verify each link
    for i in range(1, len(events)):
        expected_prev_hash = compute_event_hash(events[i - 1])
        actual_prev_hash = events[i].prev_hash

        if expected_prev_hash != actual_prev_hash:
            return VerificationResult(
                valid=False,
                broken_at_seq=i,
                error=f"Hash mismatch: expected {expected_prev_hash}, got {actual_prev_hash}"
            )

    return VerificationResult(valid=True)

@dataclass
class VerificationResult:
    valid: bool
    broken_at_seq: int | None = None
    error: str | None = None
```

**Update FileStore to Compute prev_hash**:
```python
class FileStore(EventStore):
    def append(self, event: Event) -> None:
        """Append event with automatic prev_hash computation."""
        # Check sequential constraint
        expected_seq = 0 if self._last_seq is None else self._last_seq + 1
        if event.seq != expected_seq:
            raise SequenceError(...)

        # Compute prev_hash
        if event.seq == 0:
            prev_hash = "0" * 64  # Genesis
        else:
            last_event = self._read_last_event()
            prev_hash = compute_event_hash(last_event)

        # Create new event with prev_hash
        event_with_hash = Event(
            type=event.type,
            aggregate_id=event.aggregate_id,
            seq=event.seq,
            timestamp=event.timestamp,
            payload=event.payload,
            metadata=event.metadata,
            prev_hash=prev_hash
        )

        # Append to file
        with open(self.path, 'a') as f:
            line = json.dumps(event_with_hash.__dict__) + '\n'
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        self._last_seq = event.seq
```

## CLI Commands

```bash
# Verify hash chain integrity
engine verify --log-path ./logs/universe.log

# Output (valid chain):
# Verifying hash chain...
# Genesis event: seq=0, prev_hash=0000...
# Verified 1234 events
# Hash chain: VALID
# Integrity: OK

# Output (tampered chain):
# Verifying hash chain...
# Genesis event: seq=0, prev_hash=0000...
# ERROR: Hash chain broken at seq=51
# Expected prev_hash: abc123...
# Actual prev_hash: def456...
# Integrity: FAILED

# Verify with verbose output (show each event)
engine verify --log-path ./logs/universe.log --verbose
```

## Definition of Done

- Event model updated with prev_hash field
- FileStore automatically computes prev_hash on append
- verify_chain() function implemented and tested
- All tamper detection tests pass (modified, reordered, deleted, inserted)
- CLI verify command implemented
- Performance verified: verify 10,000 events in <1 second

## Labels

`milestone:M3` `priority:critical` `type:security` `deterministic-engine`
