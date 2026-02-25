# M1: Deterministic Core

## Goal

Implement pure functional core with Event + State + Reducer pattern. This is the foundation for deterministic execution - same inputs always produce same outputs.

## Description

Create the core abstractions for deterministic state management:
- **Event**: Immutable record of state change (type, aggregate_id, seq, timestamp, payload, metadata)
- **State**: Current system state (version, aggregates dict)
- **Reducer**: Pure function that applies events to state: `(State, Event) -> State`
- **Clock**: Deterministic monotonic clock (no system time dependencies)
- **ID Generator**: Collision-free deterministic ID generation from sequence numbers

All functions must be pure (no side effects, no randomness, no system calls).

## Files to Create

- `engine/core/__init__.py`
- `engine/core/event.py` - Event dataclass
- `engine/core/state.py` - State dataclass
- `engine/core/reducer.py` - Pure reducer function
- `engine/core/clock.py` - Deterministic clock
- `engine/core/id_gen.py` - Deterministic ID generator
- `engine/tests/__init__.py`
- `engine/tests/test_reducer.py` - Reducer purity tests

## Acceptance Criteria

- [ ] Event model defined with fields: type (str), aggregate_id (str), seq (int), timestamp (int), payload (dict), metadata (dict)
- [ ] Event is immutable (frozen dataclass)
- [ ] State model defined with fields: version (int), aggregates (dict[str, dict])
- [ ] State supports multiple aggregate types (agents, tasks, teams, metrics, messages)
- [ ] Reducer function signature: `def reduce(state: State, event: Event) -> State`
- [ ] Reducer is pure: no I/O, no mutations, no randomness, no system calls
- [ ] Clock provides monotonic timestamps (deterministic, not wall-clock)
- [ ] ID generator produces unique IDs from sequence numbers (no UUIDs, no random)
- [ ] Tests verify: apply same events 100 times, get identical state every time
- [ ] Tests verify: reducer does not mutate input state (immutability check)

## Test Requirements

Create `test_reducer.py` with tests for:

1. **Determinism Test**: Apply sequence of 10 events, run 100 times, verify state hash identical
2. **Purity Test**: Verify reducer does not mutate input state object
3. **Multiple Aggregates**: Create events for different aggregate types, verify state tracks all
4. **Clock Monotonic**: Verify clock never goes backwards
5. **ID Collision**: Generate 10,000 IDs, verify all unique

```python
def test_reducer_determinism():
    """Same events applied 100 times should produce identical state."""
    events = [
        Event(type="AgentCreated", aggregate_id="agent-1", seq=0, ...),
        Event(type="TaskAssigned", aggregate_id="task-1", seq=1, ...),
        ...
    ]

    states = []
    for _ in range(100):
        state = State(version=0, aggregates={})
        for event in events:
            state = reduce(state, event)
        states.append(state)

    # All states must be identical
    assert all(s == states[0] for s in states)
    assert len(set(hash(s) for s in states)) == 1  # Same hash
```

## Implementation Notes

**Event Model**:
```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Event:
    type: str              # e.g., "AgentCreated", "TaskCompleted"
    aggregate_id: str      # e.g., "agent-1", "task-42"
    seq: int               # Global sequence number (0, 1, 2, ...)
    timestamp: int         # Monotonic timestamp (not wall-clock)
    payload: dict[str, Any]  # Event-specific data
    metadata: dict[str, Any] # Optional metadata (user, reason, etc.)
```

**State Model**:
```python
from dataclasses import dataclass, field

@dataclass
class State:
    version: int
    aggregates: dict[str, dict] = field(default_factory=dict)

    # aggregates structure:
    # {
    #   "agents": {"agent-1": {...}, "agent-2": {...}},
    #   "tasks": {"task-1": {...}},
    #   "teams": {"team-1": {...}}
    # }
```

**Reducer Function**:
```python
def reduce(state: State, event: Event) -> State:
    """
    Pure reducer: applies event to state, returns new state.

    RULES:
    - No mutations (create new State object)
    - No side effects (no I/O, no logging, no network)
    - Deterministic (same input → same output)
    """
    # Pattern match on event.type
    if event.type == "AgentCreated":
        return handle_agent_created(state, event)
    elif event.type == "TaskAssigned":
        return handle_task_assigned(state, event)
    # ... other event types
    else:
        return state  # Unknown event, no-op
```

**Deterministic Clock**:
```python
class DeterministicClock:
    """Monotonic clock that does not depend on system time."""
    def __init__(self, start_ts: int = 0):
        self._current = start_ts

    def tick(self) -> int:
        """Advance clock by 1, return new timestamp."""
        self._current += 1
        return self._current

    def now(self) -> int:
        """Get current timestamp without advancing."""
        return self._current
```

**ID Generator**:
```python
def generate_id(aggregate_type: str, seq: int) -> str:
    """
    Generate deterministic ID from aggregate type and sequence.

    Example: generate_id("agent", 42) -> "agent-42"
    """
    return f"{aggregate_type}-{seq}"
```

## Definition of Done

- All files created and committed to `evo/deterministic-engine-v2` branch
- All tests pass with 100% determinism verification
- Code review completed (no mutations, no side effects, pure functions only)
- Documentation includes examples of Event, State, and Reducer usage

## Labels

`milestone:M1` `priority:critical` `type:core` `deterministic-engine`
