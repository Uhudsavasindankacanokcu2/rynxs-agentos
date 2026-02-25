"""
EventStore abstract interface.

Defines contract for event storage implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional

from ..core.events import Event
from ..core.errors import EventStoreError
from .integrity import ZERO_HASH


@dataclass(frozen=True)
class AppendResult:
    """
    Result of an append attempt.

    When committed is False and conflict is True, the event was not written.
    """

    event: Event
    seq: Optional[int]
    event_hash: Optional[str]
    prev_hash: Optional[str]
    committed: bool
    conflict: bool
    observed_prev_hash: Optional[str] = None


class EventStore(ABC):
    """
    Abstract event storage interface.

    All implementations must guarantee:
    - Append-only (no updates, no deletes)
    - Sequential ordering (events indexed by seq)
    - Durability (fsync or equivalent)
    """

    @abstractmethod
    def append(self, event: Event, expected_prev_hash: Optional[str] = None) -> AppendResult:
        """
        Append event to log.

        Args:
            event: Event to append (seq will be assigned)

        Returns:
            AppendResult with commit/ conflict info

        Raises:
            EventStoreError: If append fails
        """
        ...

    def append_with_retry(self, event: Event, max_retries: int = 3) -> AppendResult:
        """
        Append with simple conflict retry.

        Uses get_last_hash() as the expected_prev_hash. On conflict, refreshes
        the last hash and retries up to max_retries.
        """
        expected_prev_hash = self.get_last_hash() or ZERO_HASH
        for _ in range(max_retries):
            result = self.append(event, expected_prev_hash=expected_prev_hash)
            if result.committed:
                return result
            if not result.conflict:
                raise EventStoreError("append failed without conflict")
            expected_prev_hash = self.get_last_hash() or ZERO_HASH
        raise EventStoreError("append failed after conflicts")

    @abstractmethod
    def read(self, aggregate_id: Optional[str] = None, from_seq: int = 0) -> Iterator[Event]:
        """
        Read events from log.

        Args:
            aggregate_id: Filter by aggregate ID (None = all)
            from_seq: Start from this sequence number (inclusive)

        Yields:
            Events in sequence order
        """
        ...

    def get_last_hash(self) -> Optional[str]:
        """
        Return last event hash if available.

        Implementations may override. Default returns None.
        """
        return None

    def get_event_hash(self, seq: int) -> Optional[str]:
        """
        Return event_hash for a given sequence number if available.

        Implementations may override. Default returns None.
        """
        return None
