"""
Tests for multi-writer append safety (CAS-style).

Goal: A stale expected_prev_hash must never write, and retry must commit.
"""

import json
import os
import tempfile

from engine.core.events import Event
from engine.log.file_store import FileEventStore
from engine.log.integrity import ZERO_HASH, hash_event


def _read_records(path: str):
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def _verify_chain(records):
    prev = ZERO_HASH
    for rec in records:
        ev = Event(**rec["event"])
        computed = hash_event(prev, ev)
        assert rec["prev_hash"] == prev
        assert rec["event_hash"] == computed
        prev = rec["event_hash"]


def test_append_conflict_does_not_write():
    """
    Stale expected_prev_hash must conflict and not write a new record.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        e1 = Event(type="TEST", aggregate_id="A", ts=1)
        r1 = store.append(e1, expected_prev_hash=ZERO_HASH)
        assert r1.committed
        assert r1.seq == 0

        # Stale expected_prev_hash (still ZERO_HASH)
        e2 = Event(type="TEST", aggregate_id="A", ts=2)
        r2 = store.append(e2, expected_prev_hash=ZERO_HASH)
        assert r2.conflict
        assert not r2.committed

        records = _read_records(log_path)
        assert len(records) == 1
        _verify_chain(records)


def test_multiwriter_append_with_retry():
    """
    Simulate two writers with stale hashes and ensure retry commits.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store_a = FileEventStore(log_path)
        store_b = FileEventStore(log_path)

        total = 50
        for i in range(total):
            expected = store_a.get_last_hash() or ZERO_HASH

            ev_a = Event(type="A", aggregate_id="A", ts=i)
            res_a = store_a.append(ev_a, expected_prev_hash=expected)
            assert res_a.committed

            # Writer B uses stale expected hash to force conflict
            ev_b = Event(type="B", aggregate_id="B", ts=i)
            res_b = store_b.append(ev_b, expected_prev_hash=expected)
            if res_b.conflict:
                res_b = store_b.append_with_retry(ev_b)
            assert res_b.committed

        records = _read_records(log_path)
        assert len(records) == total * 2
        seqs = [rec["event"]["seq"] for rec in records]
        assert seqs == list(range(total * 2))
        _verify_chain(records)
