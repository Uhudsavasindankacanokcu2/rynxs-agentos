"""
State model for deterministic execution.

State represents the current system state across all aggregates.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


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


@dataclass(frozen=True)
class UniverseState:
    """
    Minimal deterministic domain state for the operator.

    Stored as a single aggregate (e.g., "universe") in State.aggregates.
    """
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_seen_spec_hash: Dict[str, str] = field(default_factory=dict)
    desired: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    applied: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    failures: List[Dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def initial() -> "UniverseState":
        return UniverseState()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agents": dict(self.agents),
            "last_seen_spec_hash": dict(self.last_seen_spec_hash),
            "desired": dict(self.desired),
            "applied": dict(self.applied),
            "failures": list(self.failures),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "UniverseState":
        data = data or {}
        return UniverseState(
            agents=dict(data.get("agents", {})),
            last_seen_spec_hash=dict(data.get("last_seen_spec_hash", {})),
            desired=dict(data.get("desired", {})),
            applied=dict(data.get("applied", {})),
            failures=list(data.get("failures", [])),
        )
