# M5: Replay System

## Goal

Implement deterministic replay system that reproduces exact state from event log. Replay must be 100% deterministic: same events always produce same state. Includes tracing and diff utilities for debugging.

## Description

Create replay system with:
- **Runner**: Apply reducer to events in sequence order, produce final state
- **Trace**: Output event-by-event state transitions (for debugging)
- **Diff**: Compare two states and show field-level changes

Replay is the core of deterministic execution:
- Replay from seq 0 → reproduce entire history
- Replay from checkpoint → fast forward to specific point
- Replay with trace → debug state transitions
- Replay + diff → verify state matches checkpoint

## Files to Create

- `engine/replay/__init__.py`
- `engine/replay/runner.py` - Replay runner (apply events)
- `engine/replay/trace.py` - Trace output (event-by-event state)
- `engine/replay/diff.py` - State diff utility
- `engine/tests/test_replay.py` - Replay determinism tests
- `engine/tests/test_trace.py` - Trace output tests
- `engine/tests/test_diff.py` - Diff utility tests

## Acceptance Criteria

- [ ] `replay(events: list[Event], until_seq: int | None = None) -> State` applies reducer to each event
- [ ] Replay is deterministic: run 100 times, get identical state (same hash)
- [ ] Replay supports until_seq to stop at specific sequence
- [ ] Trace mode outputs: seq, event type, aggregate_id, state diff after event
- [ ] Trace output is human-readable (formatted JSON or table)
- [ ] Diff utility compares two State objects and shows field-level changes
- [ ] Diff supports nested dicts (aggregates contain nested agent/task data)
- [ ] Tests verify: replay 1000 events 100 times, all states identical
- [ ] Tests verify: replay to seq 500, checkpoint, replay again, states match
- [ ] Tests verify: replay with trace produces expected output format

## Test Requirements

Create `test_replay.py` with tests for:

1. **Determinism Test**: Replay 1000 events 100 times, verify all states identical
2. **Partial Replay**: Replay until_seq=500, verify state contains only events 0-500
3. **Checkpoint Resume**: Replay to 500, checkpoint, replay from checkpoint to 1000, verify state matches full replay
4. **Empty Log**: Replay empty event list, verify initial state returned
5. **Large Scale**: Replay 10,000 events, verify completes in <5 seconds
6. **State Hash Consistency**: Replay same events multiple times, verify state hash identical

```python
def test_replay_determinism():
    """Replay must be 100% deterministic across multiple runs."""
    # Create log with 1000 events
    events = [create_test_event(seq=i) for i in range(1000)]

    # Replay 100 times
    states = []
    for _ in range(100):
        state = replay(events)
        states.append(state)

    # Verify all states identical
    state_hashes = [compute_state_hash(s) for s in states]
    assert len(set(state_hashes)) == 1, "States must be identical"

    # Verify content identical (not just hash)
    for i in range(1, 100):
        assert states[i] == states[0], f"State {i} differs from state 0"
```

## Implementation Notes

**Replay Runner**:
```python
from engine.core.state import State
from engine.core.event import Event
from engine.core.reducer import reduce

def replay(events: list[Event], until_seq: int | None = None) -> State:
    """
    Replay events to produce final state.

    Args:
        events: List of events in sequence order
        until_seq: Stop replay at this sequence (inclusive). If None, replay all.

    Returns:
        Final state after applying all events
    """
    # Start with initial empty state
    state = State(version=0, aggregates={})

    # Apply each event
    for event in events:
        if until_seq is not None and event.seq > until_seq:
            break
        state = reduce(state, event)

    return state

def replay_from_checkpoint(checkpoint: Checkpoint, events: list[Event]) -> State:
    """
    Fast replay: start from checkpoint state, apply events after checkpoint.

    This is more efficient than replaying from seq 0 for large logs.
    """
    # Load state from checkpoint (deserialize)
    state = load_state_from_checkpoint(checkpoint)

    # Apply events after checkpoint
    for event in events:
        if event.seq <= checkpoint.at_seq:
            continue  # Skip events already in checkpoint
        state = reduce(state, event)

    return state
```

**Trace Output**:
```python
from typing import Any
import json

def replay_with_trace(events: list[Event], output_format: str = "table") -> State:
    """
    Replay events with trace output (event-by-event state transitions).

    Args:
        events: List of events to replay
        output_format: "table" or "json"

    Returns:
        Final state
    """
    state = State(version=0, aggregates={})

    print(f"Replaying {len(events)} events with trace...")
    print("-" * 80)

    for event in events:
        # Capture state before
        state_before = compute_state_hash(state)

        # Apply event
        state = reduce(state, event)

        # Capture state after
        state_after = compute_state_hash(state)

        # Output trace
        if output_format == "table":
            print(f"[{event.seq:6d}] {event.type:20s} {event.aggregate_id:15s} | hash: {state_after[:16]}...")
        elif output_format == "json":
            trace_entry = {
                "seq": event.seq,
                "type": event.type,
                "aggregate_id": event.aggregate_id,
                "state_hash_before": state_before,
                "state_hash_after": state_after,
                "payload": event.payload
            }
            print(json.dumps(trace_entry))

    print("-" * 80)
    print(f"Replay complete. Final state hash: {compute_state_hash(state)}")

    return state
```

**Diff Utility**:
```python
from typing import Any
from deepdiff import DeepDiff  # Or implement custom diff

def diff_states(state1: State, state2: State) -> dict[str, Any]:
    """
    Compare two states and return differences.

    Returns dict with:
    - added: fields/aggregates in state2 but not state1
    - removed: fields/aggregates in state1 but not state2
    - modified: fields with different values
    """
    # Use deepdiff library for nested dict comparison
    diff = DeepDiff(state1.aggregates, state2.aggregates, view='tree')

    return {
        "added": diff.get("dictionary_item_added", []),
        "removed": diff.get("dictionary_item_removed", []),
        "modified": diff.get("values_changed", []),
    }

def print_diff(state1: State, state2: State):
    """Print human-readable diff between two states."""
    diff = diff_states(state1, state2)

    if not any(diff.values()):
        print("States are identical (no differences)")
        return

    print("State differences:")
    print("-" * 80)

    if diff["added"]:
        print("Added:")
        for item in diff["added"]:
            print(f"  + {item}")

    if diff["removed"]:
        print("Removed:")
        for item in diff["removed"]:
            print(f"  - {item}")

    if diff["modified"]:
        print("Modified:")
        for item in diff["modified"]:
            print(f"  ~ {item}")

    print("-" * 80)
```

## CLI Commands

```bash
# Replay entire log and show final state
engine replay --log-path ./logs/universe.log

# Output:
# Replaying 1234 events...
# Final state:
#   Agents: 45
#   Tasks: 120
#   Teams: 8
#   Metrics: 340
# State hash: abc123def456...

# Replay until specific sequence
engine replay --log-path ./logs/universe.log --until-seq 1000

# Replay with trace (show each event)
engine replay --log-path ./logs/universe.log --trace --until-seq 10

# Output:
# Replaying 10 events with trace...
# --------------------------------------------------------------------------------
# [     0] AgentCreated         agent-1         | hash: abc123def456...
# [     1] TaskAssigned         task-1          | hash: 789012abc345...
# [     2] TaskCompleted        task-1          | hash: def678901234...
# ...
# --------------------------------------------------------------------------------
# Replay complete. Final state hash: xyz789...

# Replay and compare with checkpoint
engine replay --log-path ./logs/universe.log \
  --until-seq 1000 \
  --diff-with ./checkpoints/checkpoint-1000.checkpoint

# Output:
# Replaying 1000 events...
# Final state hash: abc123...
#
# Comparing with checkpoint checkpoint-1000...
# Checkpoint state hash: abc123...
#
# State diff: MATCH (no differences)
# Deterministic replay: VERIFIED

# Replay from checkpoint (fast forward)
engine replay --log-path ./logs/universe.log \
  --from-checkpoint ./checkpoints/checkpoint-1000.checkpoint \
  --until-seq 2000

# Output:
# Loading checkpoint checkpoint-1000 (at seq 1000)...
# Replaying 1000 events (1001 to 2000)...
# Final state hash: def456...
# Performance: 0.5s (vs 2.1s from seq 0)
```

## Definition of Done

- Replay runner implemented with determinism guarantee
- Trace output produces readable event-by-event transitions
- Diff utility compares states and shows field-level changes
- All tests pass (determinism, partial replay, checkpoint resume)
- CLI commands implemented (replay, trace, diff-with)
- Performance verified: 10,000 events replay in <5 seconds
- Documentation includes examples of replay workflow

## Labels

`milestone:M5` `priority:critical` `type:core` `deterministic-engine`
