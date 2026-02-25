"""
EventStore abstract interface.

Defines contract for event storage implementations.
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional
from ..core.events import Event


class EventStore(ABC):
    """
    Abstract event storage interface.

    All implementations must guarantee:
    - Append-only (no updates, no deletes)
    - Sequential ordering (events indexed by seq)
    - Durability (fsync or equivalent)
    """

    @abstractmethod
    def append(self, event: Event) -> Event:
        """
        Append event to log.

        Args:
            event: Event to append (seq will be assigned)

        Returns:
            Event with seq assigned

        Raises:
            EventStoreError: If append fails
        """
        ...

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

    def get_event_hash(self, seq: int) -> Optional[str]:
        """
        Return event_hash for a given sequence number if available.

        Implementations may override. Default returns None.
        """
        return None
