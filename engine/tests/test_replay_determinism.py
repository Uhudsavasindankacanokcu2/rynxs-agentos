"""
Tests for replay determinism.

Critical: Replay must produce identical state across multiple runs.
"""

import tempfile
import os
from engine.core.reducer import Reducer
from engine.core.events import Event
from engine.core.canonical import canonical_json_str
from engine.log.file_store import FileEventStore
from engine.replay.runner import replay


def test_replay_determinism_100_runs():
    """Replay same events 100 times must produce identical state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        # Create reducer
        r = Reducer()

        def inc_handler(cur, ev):
            cur = cur or {"n": 0}
            return {"n": cur["n"] + ev.payload["inc"]}

        r.register("INC", inc_handler)

        # Append 10 events
        for i in range(10):
            e = Event(type="INC", aggregate_id="A", ts=i, payload={"inc": i})
            store.append(e)

        # Replay 100 times
        results = []
        for _ in range(100):
            result = replay(store, r)
            results.append(canonical_json_str(result.state.aggregates))

        # All results must be identical
        assert len(set(results)) == 1

        # Verify final value: 0+1+2+...+9 = 45
        final = replay(store, r)
        assert final.state.get_agg("A") == {"n": 45}
        assert final.applied == 10


def test_replay_partial():
    """Replay to specific sequence must be deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        r = Reducer()

        def set_handler(cur, ev):
            return {"val": ev.payload["val"]}

        r.register("SET", set_handler)

        # Append 20 events
        for i in range(20):
            e = Event(type="SET", aggregate_id="A", ts=i, payload={"val": i})
            store.append(e)

        # Replay to seq 9 (10 events: 0-9)
        result1 = replay(store, r, to_seq=9)
        result2 = replay(store, r, to_seq=9)

        assert result1.applied == 10
        assert result2.applied == 10
        assert canonical_json_str(result1.state.aggregates) == canonical_json_str(result2.state.aggregates)
        assert result1.state.get_agg("A") == {"val": 9}


def test_replay_empty_log():
    """Replay empty log must return initial state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "empty.log")
        store = FileEventStore(log_path)

        r = Reducer()

        result = replay(store, r)

        assert result.applied == 0
        assert result.state.version == 0
        assert result.state.aggregates == {}


def test_replay_aggregate_filter():
    """Replay with aggregate filter must be deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        r = Reducer()

        def inc_handler(cur, ev):
            cur = cur or {"n": 0}
            return {"n": cur["n"] + 1}

        r.register("INC", inc_handler)

        # Append events for two aggregates
        for i in range(10):
            store.append(Event(type="INC", aggregate_id="A", ts=i * 2))
            store.append(Event(type="INC", aggregate_id="B", ts=i * 2 + 1))

        # Replay only aggregate A
        result = replay(store, r, aggregate_id="A")

        assert result.applied == 10
        assert result.state.get_agg("A") == {"n": 10}
        assert result.state.get_agg("B") is None
