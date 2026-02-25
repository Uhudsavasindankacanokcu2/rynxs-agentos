"""
Tests for reducer purity and determinism.

Critical: Reducer must be pure (no side effects, deterministic).
"""

from engine.core.reducer import Reducer
from engine.core.events import Event
from engine.core.state import State
from engine.core.canonical import canonical_json_str


def test_reducer_deterministic_output():
    """Same (state, event) must produce same output."""
    r = Reducer()

    def handler(cur, ev):
        cur = cur or {"n": 0}
        return {"n": cur["n"] + ev.payload["inc"]}

    r.register("INC", handler)

    s0 = State()
    e = Event(type="INC", aggregate_id="A", ts=1, payload={"inc": 2})

    s1 = r.apply(s0, e)
    s2 = r.apply(s0, e)

    assert canonical_json_str(s1.aggregates) == canonical_json_str(s2.aggregates)


def test_reducer_multiple_applies():
    """Applying same event 100 times must produce identical result."""
    r = Reducer()

    def handler(cur, ev):
        cur = cur or {"count": 0}
        return {"count": cur["count"] + 1}

    r.register("COUNT", handler)

    s0 = State()
    e = Event(type="COUNT", aggregate_id="counter", ts=1)

    results = []
    for _ in range(100):
        s = r.apply(s0, e)
        results.append(canonical_json_str(s.aggregates))

    # All results must be identical
    assert len(set(results)) == 1


def test_reducer_immutability():
    """Reducer must not mutate input state."""
    r = Reducer()

    def handler(cur, ev):
        return {"value": ev.payload["val"]}

    r.register("SET", handler)

    s0 = State()
    original_aggs = s0.aggregates

    e = Event(type="SET", aggregate_id="test", ts=1, payload={"val": 42})
    s1 = r.apply(s0, e)

    # Original state unchanged
    assert s0.aggregates is original_aggs
    assert s0.version == 0

    # New state has changes
    assert s1.version == 1
    assert s1.get_agg("test") == {"value": 42}


def test_reducer_sequence_determinism():
    """Sequence of events must produce deterministic result."""
    r = Reducer()

    def inc_handler(cur, ev):
        cur = cur or {"n": 0}
        return {"n": cur["n"] + ev.payload["inc"]}

    def mul_handler(cur, ev):
        cur = cur or {"n": 0}
        return {"n": cur["n"] * ev.payload["mul"]}

    r.register("INC", inc_handler)
    r.register("MUL", mul_handler)

    events = [
        Event(type="INC", aggregate_id="A", ts=1, payload={"inc": 5}),
        Event(type="MUL", aggregate_id="A", ts=2, payload={"mul": 2}),
        Event(type="INC", aggregate_id="A", ts=3, payload={"inc": 3}),
    ]

    # Apply sequence 10 times
    results = []
    for _ in range(10):
        s = State()
        for e in events:
            s = r.apply(s, e)
        results.append(canonical_json_str(s.aggregates))

    # All results identical
    assert len(set(results)) == 1

    # Final value: (0+5)*2+3 = 13
    final_state = State()
    for e in events:
        final_state = r.apply(final_state, e)
    assert final_state.get_agg("A") == {"n": 13}
