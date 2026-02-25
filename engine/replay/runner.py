"""
Replay runner: reconstruct state from event log.

Replay is pure: applies reducer to each event in sequence order.
"""

from dataclasses import dataclass
from typing import Optional
from ..core.state import State
from ..core.reducer import Reducer
from ..log.store import EventStore


@dataclass(frozen=True)
class ReplayResult:
    """
    Result of replay operation.

    Fields:
        state: Final state after applying events
        applied: Number of events applied
    """
    state: State
    applied: int


def replay(
    store: EventStore,
    reducer: Reducer,
    aggregate_id: Optional[str] = None,
    to_seq: Optional[int] = None
) -> ReplayResult:
    """
    Replay events to reconstruct state.

    This is the core of deterministic execution. Same events always
    produce same state.

    Args:
        store: Event store to read from
        reducer: Reducer with registered handlers
        aggregate_id: Filter by aggregate ID (None = all)
        to_seq: Stop at this sequence (inclusive, None = all)

    Returns:
        ReplayResult with final state and count
    """
    st = State()
    count = 0

    for ev in store.read(aggregate_id=aggregate_id, from_seq=0):
        if to_seq is not None and ev.require_seq() > to_seq:
            break
        st = reducer.apply(st, ev)
        count += 1

    return ReplayResult(state=st, applied=count)
