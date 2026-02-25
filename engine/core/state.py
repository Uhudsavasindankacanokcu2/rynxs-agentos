"""
State model for deterministic execution.

State represents the current system state across all aggregates.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class State:
    """
    Immutable state container.

    Fields:
        version: Monotonic version number (increments with each event)
        aggregates: Dict of aggregate_id -> aggregate_state

    State is immutable. Use with_agg() to create new state with updated aggregate.
    """
    version: int = 0
    aggregates: Dict[str, Any] = field(default_factory=dict)

    def get_agg(self, aggregate_id: str) -> Any:
        """
        Get aggregate state by ID.

        Returns:
            Aggregate state or None if not found
        """
        return self.aggregates.get(aggregate_id)

    def with_agg(self, aggregate_id: str, agg_state: Any) -> "State":
        """
        Create new state with updated aggregate.

        Since State is immutable, this returns a new State instance.

        Args:
            aggregate_id: Aggregate identifier
            agg_state: New aggregate state

        Returns:
            New State with updated aggregate and incremented version
        """
        new_aggs = dict(self.aggregates)
        new_aggs[aggregate_id] = agg_state
        return State(version=self.version + 1, aggregates=new_aggs)
