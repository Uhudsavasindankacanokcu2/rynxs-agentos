"""
Core deterministic execution primitives.

This module provides the foundational abstractions for deterministic state management:
- Event: Immutable state change records
- State: Current system state
- Reducer: Pure functions for state transitions
- Canonical: Deterministic serialization
- Clock: Deterministic time source
- IDs: Stable identifier generation
"""

from .events import Event
from .state import State, UniverseState
from .reducer import Reducer
from .canonical import canonicalize, canonical_json_bytes, canonical_json_str
from .clock import DeterministicClock
from .ids import stable_id
from .errors import DeterminismError, InvalidTransitionError, IntegrityError, EventStoreError

__all__ = [
    "Event",
    "State",
    "UniverseState",
    "Reducer",
    "canonicalize",
    "canonical_json_bytes",
    "canonical_json_str",
    "DeterministicClock",
    "stable_id",
    "DeterminismError",
    "InvalidTransitionError",
    "IntegrityError",
    "EventStoreError",
]
