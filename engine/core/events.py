"""
Event model for deterministic state transitions.

Events are immutable records of state changes.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Event:
    """
    Immutable event record.

    Fields:
        type: Event type (e.g., "AgentCreated", "TaskCompleted")
        aggregate_id: Target aggregate identifier
        ts: Timestamp (monotonic, from deterministic clock)
        payload: Event-specific data
        meta: Metadata (user, reason, etc.)
        seq: Sequence number (assigned by EventStore)
    """
    type: str
    aggregate_id: str
    ts: int
    payload: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    seq: Optional[int] = None

    def require_seq(self) -> int:
        """
        Get sequence number or raise error if not assigned.

        Raises:
            ValueError: If seq is None
        """
        if self.seq is None:
            raise ValueError("Event.seq is required but None")
        return self.seq
