"""
File-based event store using append-only JSONL format.

Each line is a hash chain record with prev_hash, event_hash, and event data.
"""

import os
import json
from typing import Iterator, Optional, Tuple
from ..core.events import Event
from ..core.canonical import canonical_json_str
from ..core.errors import EventStoreError
from .store import EventStore
from .integrity import ZERO_HASH, chain_record

try:
    import fcntl
except ImportError:  # Windows or unsupported platform
    fcntl = None

class FileEventStore(EventStore):
    """
    File-based append-only event store.

    Storage format: JSONL (newline-delimited JSON)
    Each line: {"prev_hash": "...", "event_hash": "...", "event": {...}}

    Guarantees:
    - Append-only (no mutations)
    - Fsync after each append (durability)
    - Hash chain integrity
    """

    def __init__(self, path: str) -> None:
        """
        Initialize file event store.

        Args:
            path: Path to JSONL file
        """
        self.path = path

        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # Create empty file if not exists
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(b"")

    def _last_seq_and_hash(self, f) -> Tuple[int, str]:
        """
        Read last sequence number and hash from log.

        Returns:
            (last_seq, last_hash) tuple
            (-1, ZERO_HASH) if log is empty
        """
        last_seq = -1
        last_hash = ZERO_HASH

        f.seek(0)
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            last_seq = rec["event"]["seq"]
            last_hash = rec["event_hash"]

        return last_seq, last_hash

    def append(self, event: Event) -> Event:
        """
        Append event to log with hash chain.

        Args:
            event: Event to append (seq will be assigned)

        Returns:
            Event with seq assigned

        Raises:
            EventStoreError: If append fails
        """
        try:
            with open(self.path, "a+b") as f:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                last_seq, last_hash = self._last_seq_and_hash(f)
                seq = last_seq + 1

                # Create new event with assigned seq
                e2 = Event(
                    type=event.type,
                    aggregate_id=event.aggregate_id,
                    seq=seq,
                    ts=event.ts,
                    payload=event.payload,
                    meta=event.meta,
                )

                # Create hash chain record
                rec = chain_record(last_hash, e2)
                line = canonical_json_str(rec) + "\n"

                # Append with fsync (durability guarantee)
                f.seek(0, os.SEEK_END)
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())

                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as ex:
            raise EventStoreError(str(ex)) from ex

        return e2

    def read(self, aggregate_id: Optional[str] = None, from_seq: int = 0) -> Iterator[Event]:
        """
        Read events from log.

        Args:
            aggregate_id: Filter by aggregate ID (None = all)
            from_seq: Start from this sequence (inclusive)

        Yields:
            Events in sequence order
        """
        with open(self.path, "rb") as f:
            for line in f:
                if not line.strip():
                    continue

                rec = json.loads(line)
                ev = rec["event"]

                # Apply filters
                if ev["seq"] < from_seq:
                    continue
                if aggregate_id is not None and ev["aggregate_id"] != aggregate_id:
                    continue

                yield Event(
                    type=ev["type"],
                    aggregate_id=ev["aggregate_id"],
                    seq=ev["seq"],
                    ts=ev["ts"],
                    payload=ev.get("payload", {}),
                    meta=ev.get("meta", {}),
                )

    def get_event_hash(self, seq: int) -> Optional[str]:
        """
        Return event_hash for a given seq.
        """
        with open(self.path, "rb") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                ev = rec.get("event", {})
                if ev.get("seq") == seq:
                    return rec.get("event_hash")
        return None
