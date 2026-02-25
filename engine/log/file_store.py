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
from .store import EventStore, AppendResult
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
        self.max_bytes = self._env_int("EVENT_STORE_MAX_BYTES")
        self.max_segments = self._env_int("EVENT_STORE_MAX_SEGMENTS")
        self.segment_prefix = f"{self.path}.seg-"
        self.head_path = f"{self.path}.head.json"

        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # Create empty file if not exists
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(b"")

    def _env_int(self, key: str) -> Optional[int]:
        val = os.getenv(key)
        if not val:
            return None
        try:
            parsed = int(val)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def _read_head(self) -> Optional[Tuple[int, str, int]]:
        if not os.path.exists(self.head_path):
            return None
        try:
            with open(self.head_path, "r") as f:
                data = json.load(f)
            return int(data.get("last_seq", -1)), str(data.get("last_hash", ZERO_HASH)), int(
                data.get("segment_index", 0)
            )
        except (OSError, ValueError, TypeError):
            return None

    def _write_head(self, last_seq: int, last_hash: str, segment_index: int) -> None:
        data = {"last_seq": last_seq, "last_hash": last_hash, "segment_index": segment_index}
        with open(self.head_path, "w") as f:
            f.write(canonical_json_str(data))

    def _segment_paths(self) -> list:
        segments = []
        prefix = self.segment_prefix
        for name in os.listdir(os.path.dirname(self.path) or "."):
            if not name.startswith(os.path.basename(prefix)):
                continue
            segments.append(os.path.join(os.path.dirname(self.path) or ".", name))
        segments.sort(key=self._segment_index)
        return segments

    def _segment_index(self, path: str) -> int:
        base = os.path.basename(path)
        if not base.startswith(os.path.basename(self.segment_prefix)):
            return -1
        suffix = base[len(os.path.basename(self.segment_prefix)) :]
        try:
            return int(suffix)
        except ValueError:
            return -1

    def _next_segment_index(self) -> int:
        head = self._read_head()
        if head:
            return head[2] + 1
        segments = self._segment_paths()
        if not segments:
            return 1
        return max(self._segment_index(p) for p in segments) + 1

    def _should_rotate(self, f) -> bool:
        if not self.max_bytes:
            return False
        f.seek(0, os.SEEK_END)
        return f.tell() >= self.max_bytes

    def _rotate(self, last_seq: int, last_hash: str) -> None:
        seg_index = self._next_segment_index()
        seg_path = f"{self.segment_prefix}{seg_index:06d}"
        if os.path.getsize(self.path) > 0:
            os.replace(self.path, seg_path)
        else:
            with open(seg_path, "wb") as f:
                f.write(b"")
        with open(self.path, "wb") as f:
            f.write(b"")
        self._write_head(last_seq, last_hash, seg_index)

        if self.max_segments:
            segments = self._segment_paths()
            if len(segments) > self.max_segments:
                for old in segments[: len(segments) - self.max_segments]:
                    try:
                        os.remove(old)
                    except OSError:
                        pass

    def _last_seq_and_hash(self, f) -> Tuple[int, str]:
        """
        Read last sequence number and hash from log.

        Returns:
            (last_seq, last_hash) tuple
            (-1, ZERO_HASH) if log is empty
        """
        last_seq = -1
        last_hash = ZERO_HASH

        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            head = self._read_head()
            if head:
                return head[0], head[1]
        f.seek(0)
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            last_seq = rec["event"]["seq"]
            last_hash = rec["event_hash"]

        return last_seq, last_hash

    def append(self, event: Event, expected_prev_hash: Optional[str] = None) -> AppendResult:
        """
        Append event to log with hash chain.

        Args:
            event: Event to append (seq will be assigned)

        Returns:
            AppendResult with commit/ conflict info

        Raises:
            EventStoreError: If append fails
        """
        try:
            with open(self.path, "a+b") as f:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                last_seq, last_hash = self._last_seq_and_hash(f)

                if self._should_rotate(f):
                    if fcntl:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    f.close()
                    self._rotate(last_seq, last_hash)
                    with open(self.path, "a+b") as f2:
                        if fcntl:
                            fcntl.flock(f2.fileno(), fcntl.LOCK_EX)
                        last_seq, last_hash = self._last_seq_and_hash(f2)
                        return self._append_locked(f2, event, expected_prev_hash, last_seq, last_hash)

                return self._append_locked(f, event, expected_prev_hash, last_seq, last_hash)
        except OSError as ex:
            raise EventStoreError(str(ex)) from ex

    def _append_locked(
        self,
        f,
        event: Event,
        expected_prev_hash: Optional[str],
        last_seq: int,
        last_hash: str,
    ) -> AppendResult:
        if expected_prev_hash is not None and expected_prev_hash != last_hash:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return AppendResult(
                event=event,
                seq=None,
                event_hash=None,
                prev_hash=None,
                committed=False,
                conflict=True,
                observed_prev_hash=last_hash,
            )

        seq = last_seq + 1
        hash_version = event.hash_version
        env_hash_version = os.getenv("RYNXS_HASH_VERSION")
        if env_hash_version:
            env_val = env_hash_version.strip().lower()
            if env_val not in ("v1", "v2"):
                raise EventStoreError(f"unsupported hash version: {env_hash_version}")
            if hash_version and env_val != hash_version:
                raise EventStoreError(
                    f"hash version mismatch: env={env_val} event={hash_version}"
                )
            if env_val == "v2":
                hash_version = "v2"
            elif env_val == "v1":
                hash_version = None
        elif not hash_version:
            hash_version = None

        e2 = Event(
            type=event.type,
            aggregate_id=event.aggregate_id,
            seq=seq,
            ts=event.ts,
            payload=event.payload,
            meta=event.meta,
            hash_version=hash_version,
        )

        rec = chain_record(last_hash, e2)
        line = canonical_json_str(rec) + "\n"

        f.seek(0, os.SEEK_END)
        f.write(line.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())

        if fcntl:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return AppendResult(
            event=e2,
            seq=seq,
            event_hash=rec.get("event_hash"),
            prev_hash=last_hash,
            committed=True,
            conflict=False,
            observed_prev_hash=last_hash,
        )

    def read(self, aggregate_id: Optional[str] = None, from_seq: int = 0) -> Iterator[Event]:
        """
        Read events from log.

        Args:
            aggregate_id: Filter by aggregate ID (None = all)
            from_seq: Start from this sequence (inclusive)

        Yields:
            Events in sequence order
        """
        for path in self._segment_paths() + [self.path]:
            with open(path, "rb") as f:
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
                        hash_version=ev.get("hash_version"),
                    )

    def get_event_hash(self, seq: int) -> Optional[str]:
        """
        Return event_hash for a given seq.
        """
        for path in self._segment_paths() + [self.path]:
            with open(path, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    ev = rec.get("event", {})
                    if ev.get("seq") == seq:
                        return rec.get("event_hash")
        return None

    def get_last_hash(self) -> Optional[str]:
        with open(self.path, "rb") as f:
            _, last_hash = self._last_seq_and_hash(f)
        return last_hash
