"""
Tests for hash chain integrity.

Critical: Hash chain must detect any tampering.
"""

import tempfile
import os
import json
from engine.core.events import Event
from engine.log.file_store import FileEventStore
from engine.log.integrity import ZERO_HASH, hash_event


def test_genesis_event_has_zero_hash():
    """First event must chain to ZERO_HASH."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        e = Event(type="TEST", aggregate_id="A", ts=1)
        store.append(e)

        # Read raw JSONL
        with open(log_path, "r") as f:
            line = f.readline()
            rec = json.loads(line)

        assert rec["prev_hash"] == ZERO_HASH


def test_hash_chain_links():
    """Each event must chain to previous event hash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        # Append 5 events
        for i in range(5):
            e = Event(type="TEST", aggregate_id="A", ts=i)
            store.append(e)

        # Read and verify chain
        with open(log_path, "r") as f:
            lines = f.readlines()

        records = [json.loads(line) for line in lines]

        # Verify each link
        for i in range(1, len(records)):
            prev_rec = records[i - 1]
            curr_rec = records[i]

            assert curr_rec["prev_hash"] == prev_rec["event_hash"]


def test_hash_determinism():
    """Same event must produce same hash."""
    e = Event(type="TEST", aggregate_id="A", seq=0, ts=1, payload={"val": 42})

    h1 = hash_event(ZERO_HASH, e)
    h2 = hash_event(ZERO_HASH, e)

    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_tamper_detection_modified_payload():
    """Modifying event payload must change hash."""
    e1 = Event(type="TEST", aggregate_id="A", seq=0, ts=1, payload={"val": 42})
    e2 = Event(type="TEST", aggregate_id="A", seq=0, ts=1, payload={"val": 99})

    h1 = hash_event(ZERO_HASH, e1)
    h2 = hash_event(ZERO_HASH, e2)

    assert h1 != h2


def test_tamper_detection_reordered_keys():
    """Dict key order in payload must not affect hash (canonical)."""
    e1 = Event(type="TEST", aggregate_id="A", seq=0, ts=1, payload={"a": 1, "b": 2})
    e2 = Event(type="TEST", aggregate_id="A", seq=0, ts=1, payload={"b": 2, "a": 1})

    h1 = hash_event(ZERO_HASH, e1)
    h2 = hash_event(ZERO_HASH, e2)

    # Canonical serialization ensures same hash
    assert h1 == h2


def test_hash_chain_break_detection():
    """Breaking hash chain must be detectable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        # Append 10 events
        for i in range(10):
            e = Event(type="TEST", aggregate_id="A", ts=i)
            store.append(e)

        # Read records
        with open(log_path, "r") as f:
            lines = f.readlines()

        records = [json.loads(line) for line in lines]

        # Tamper: modify event 5 payload
        records[5]["event"]["payload"] = {"tampered": True}

        # Write back
        with open(log_path, "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        # Verify chain manually
        prev_hash = ZERO_HASH
        chain_valid = True
        broken_at = None

        for i, rec in enumerate(records):
            expected_prev = prev_hash
            actual_prev = rec["prev_hash"]

            if expected_prev != actual_prev:
                chain_valid = False
                broken_at = i
                break

            # Recompute hash
            ev = Event(**rec["event"])
            computed_hash = hash_event(prev_hash, ev)

            if computed_hash != rec["event_hash"]:
                chain_valid = False
                broken_at = i
                break

            prev_hash = rec["event_hash"]

        # Chain should break at event 5
        assert not chain_valid
        assert broken_at == 5
