# M2: Append-Only EventStore

## Goal

Implement persistent event log with file-based backend. Events are append-only (no updates, no deletes) to guarantee immutability and auditability.

## Description

Create EventStore interface and file-based implementation for storing events:
- **EventStore**: Abstract interface for append, read, query operations
- **FileStore**: File-based implementation using newline-delimited JSON (JSONL)
- **SQLiteStore**: SQLite implementation for future scalability (optional for M2)

The EventStore must guarantee:
- Append-only (no mutations to existing entries)
- Sequential ordering (events indexed by seq)
- Idempotency (duplicate seq rejected)
- Crash-safe (fsync after append)

## Files to Create

- `engine/log/__init__.py`
- `engine/log/event_store.py` - EventStore interface (abstract base class)
- `engine/log/file_store.py` - File-based implementation (JSONL)
- `engine/log/sqlite_store.py` - SQLite implementation (optional)
- `engine/tests/test_event_store.py` - EventStore tests
- `engine/tests/test_file_store.py` - FileStore-specific tests

## Acceptance Criteria

- [ ] EventStore interface defines: `append(event: Event)`, `read_all() -> list[Event]`, `get_since_seq(seq: int) -> list[Event]`
- [ ] FileStore stores events as newline-delimited JSON (one event per line)
- [ ] Append operation checks: event.seq must be next_expected_seq (no gaps, no duplicates)
- [ ] Append operation calls fsync() to ensure durability
- [ ] Read operations return events in ascending seq order
- [ ] get_since_seq(100) returns events with seq >= 100
- [ ] Append is idempotent: appending same seq twice raises DuplicateSeqError
- [ ] Tests verify: append 1000 events, read_all, verify all present and ordered
- [ ] Tests verify: crash simulation (append, kill, restart, verify last event present)

## Test Requirements

Create `test_event_store.py` with tests for:

1. **Append and Read**: Append 100 events, read all, verify count and order
2. **Idempotency**: Append event with seq=5, attempt duplicate append, verify error raised
3. **Sequential Constraint**: Attempt to append seq=10 when next expected is 5, verify error
4. **Query Since Seq**: Append 100 events, query since seq=50, verify 50 events returned
5. **Crash Safety**: Append events, simulate crash (close without cleanup), reopen, verify events present
6. **Large Log**: Append 10,000 events, verify read performance acceptable (<1 second)

```python
def test_append_and_read():
    """Append events and verify read returns all in order."""
    store = FileStore(path="./test.log")
    events = [create_test_event(seq=i) for i in range(100)]

    for event in events:
        store.append(event)

    read_events = store.read_all()
    assert len(read_events) == 100
    assert [e.seq for e in read_events] == list(range(100))
```

## Implementation Notes

**EventStore Interface**:
```python
from abc import ABC, abstractmethod
from engine.core.event import Event

class EventStore(ABC):
    """Abstract interface for event storage."""

    @abstractmethod
    def append(self, event: Event) -> None:
        """
        Append event to log. Must be sequential (no gaps).
        Raises DuplicateSeqError if seq already exists.
        Raises SequenceGapError if seq != next_expected_seq.
        """
        pass

    @abstractmethod
    def read_all(self) -> list[Event]:
        """Read all events in seq order."""
        pass

    @abstractmethod
    def get_since_seq(self, seq: int) -> list[Event]:
        """Get all events with seq >= seq."""
        pass

    @abstractmethod
    def get_last_seq(self) -> int | None:
        """Get sequence number of last event (None if empty)."""
        pass
```

**FileStore Implementation**:
```python
import json
import os
from pathlib import Path
from engine.core.event import Event
from engine.log.event_store import EventStore

class FileStore(EventStore):
    """File-based event store using JSONL format."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_last_seq()

    def _cache_last_seq(self):
        """Read last line to determine last seq (for performance)."""
        if not self.path.exists():
            self._last_seq = None
            return

        with open(self.path, 'rb') as f:
            # Seek to end and read last line
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
                last_line = f.readline().decode()
                event_data = json.loads(last_line)
                self._last_seq = event_data['seq']
            except:
                self._last_seq = None

    def append(self, event: Event) -> None:
        """Append event to log file."""
        # Check sequential constraint
        expected_seq = 0 if self._last_seq is None else self._last_seq + 1
        if event.seq != expected_seq:
            if event.seq < expected_seq:
                raise DuplicateSeqError(f"Event seq {event.seq} already exists")
            else:
                raise SequenceGapError(f"Expected seq {expected_seq}, got {event.seq}")

        # Serialize and append
        with open(self.path, 'a') as f:
            line = json.dumps(event.__dict__) + '\n'
            f.write(line)
            f.flush()
            os.fsync(f.fileno())  # Ensure durability

        self._last_seq = event.seq

    def read_all(self) -> list[Event]:
        """Read all events from log file."""
        if not self.path.exists():
            return []

        events = []
        with open(self.path, 'r') as f:
            for line in f:
                event_data = json.loads(line)
                events.append(Event(**event_data))
        return events

    def get_since_seq(self, seq: int) -> list[Event]:
        """Get events with seq >= seq."""
        return [e for e in self.read_all() if e.seq >= seq]

    def get_last_seq(self) -> int | None:
        """Get last sequence number."""
        return self._last_seq
```

**Custom Exceptions**:
```python
class DuplicateSeqError(Exception):
    """Raised when attempting to append duplicate sequence number."""
    pass

class SequenceGapError(Exception):
    """Raised when attempting to append non-sequential event."""
    pass
```

## CLI Commands

```bash
# Initialize new event log
engine init --log-path ./logs/universe.log

# Append event to log
engine append --log-path ./logs/universe.log \
  --type AgentCreated \
  --aggregate-id agent-1 \
  --payload '{"name":"alpha","model":"claude-sonnet-4"}' \
  --metadata '{"user":"admin","reason":"initial-setup"}'

# Read all events
engine read --log-path ./logs/universe.log

# Read events since sequence 100
engine read --log-path ./logs/universe.log --since-seq 100
```

## Definition of Done

- All files created and committed to `evo/deterministic-engine-v2` branch
- All tests pass (append, read, idempotency, sequential constraint, crash safety)
- FileStore implementation complete with fsync durability guarantee
- CLI commands implemented and tested (init, append, read)
- Performance verified: 10,000 events append + read in <2 seconds

## Labels

`milestone:M2` `priority:critical` `type:storage` `deterministic-engine`
