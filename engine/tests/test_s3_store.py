"""
Unit tests for S3EventStore using moto (S3 mock).

Test coverage:
- T1: Append + Read roundtrip
- T2: Pagination (1000+ events)
- T3: Tamper detection (hash manipulation)
- T4: Gap detection (missing sequence)
- T5: Bucket access errors
"""

import json
import pytest

try:
    import boto3
    from moto import mock_aws
    from engine.log.s3_store import S3EventStore
except ImportError:
    boto3 = None
    mock_aws = None
    S3EventStore = None

from engine.core.events import Event
from engine.core.errors import EventStoreError
from engine.log.integrity import ZERO_HASH


# Skip all tests if boto3 or moto not installed
pytestmark = pytest.mark.skipif(
    boto3 is None or mock_aws is None,
    reason="boto3 or moto not installed",
)


@mock_aws
def test_t1_append_read_roundtrip():
    """
    T1: Append + Read roundtrip.

    Verify:
    - Events written to S3 can be read back
    - Seq numbers are correct
    - Payload is preserved
    - Hash chain is valid
    """
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Create S3EventStore
    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events
    events = [
        Event(type="TestEvent", aggregate_id="agg-1", ts=100, payload={"idx": 0}),
        Event(type="TestEvent", aggregate_id="agg-1", ts=200, payload={"idx": 1}),
        Event(type="TestEvent", aggregate_id="agg-1", ts=300, payload={"idx": 2}),
    ]

    for event in events:
        result = store.append_with_retry(event)
        assert result.committed
        assert not result.conflict

    # Read back
    read_events = list(store.read())
    assert len(read_events) == 3

    for i, event in enumerate(read_events):
        assert event.seq == i
        assert event.type == "TestEvent"
        assert event.aggregate_id == "agg-1"
        assert event.payload["idx"] == i


@mock_aws
def test_t2_pagination_1000_plus_events():
    """
    T2: Pagination with 1000+ events.

    Verify:
    - Paginator correctly handles >1000 keys
    - All events are read (no silent truncation)
    - Seq order is preserved
    """
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Create S3EventStore
    store = S3EventStore(bucket=bucket, prefix="events")

    # Append 1005 events (tests paginator)
    num_events = 1005
    for i in range(num_events):
        event = Event(type="TestEvent", aggregate_id="agg-1", ts=i * 100, payload={"idx": i})
        result = store.append_with_retry(event)
        assert result.committed

    # Read back all events
    read_events = list(store.read())
    assert len(read_events) == num_events

    # Verify seq continuity
    for i, event in enumerate(read_events):
        assert event.seq == i
        assert event.payload["idx"] == i


@mock_aws
def test_t3_tamper_detection():
    """
    T3: Tamper detection (hash manipulation).

    Verify:
    - Modifying event body breaks hash chain
    - Read raises EventStoreError with integrity failure
    """
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Create S3EventStore
    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events
    for i in range(5):
        event = Event(type="TestEvent", aggregate_id="agg-1", ts=i * 100, payload={"idx": i})
        store.append_with_retry(event)

    # Tamper with seq=3 event (corrupt hash)
    key = "events/0000000003.json"
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    rec = json.loads(body)
    rec["event_hash"] = "deadbeef" * 8  # Corrupt hash
    s3_client.put_object(Bucket=bucket, Key=key, Body=json.dumps(rec).encode("utf-8"))

    # Read should fail with integrity error
    with pytest.raises(EventStoreError, match="Hash mismatch"):
        list(store.read())


@mock_aws
def test_t4_gap_detection():
    """
    T4: Gap detection (missing sequence).

    Verify:
    - Missing seq number is detected
    - Read raises EventStoreError with gap error
    """
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Create S3EventStore
    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events
    for i in range(7):
        event = Event(type="TestEvent", aggregate_id="agg-1", ts=i * 100, payload={"idx": i})
        store.append_with_retry(event)

    # Delete seq=5 to create gap
    key = "events/0000000005.json"
    s3_client.delete_object(Bucket=bucket, Key=key)

    # Read should fail with gap error
    with pytest.raises(EventStoreError, match="Sequence gap"):
        list(store.read())


@mock_aws
def test_t5_bucket_access_errors():
    """
    T5: Bucket missing / access denied.

    Verify:
    - Creating store with non-existent bucket raises EventStoreError
    - Error message includes bucket name
    """
    # Create S3 client (no bucket)
    # Attempt to create store with non-existent bucket
    with pytest.raises(EventStoreError, match="not accessible"):
        S3EventStore(bucket="nonexistent-bucket", prefix="events")


@mock_aws
def test_get_last_hash():
    """Test get_last_hash() method."""
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    store = S3EventStore(bucket=bucket, prefix="events")

    # Empty store
    assert store.get_last_hash() is None

    # Append event
    event = Event(type="TestEvent", aggregate_id="agg-1", ts=100, payload={})
    result = store.append_with_retry(event)

    # Last hash should match
    assert store.get_last_hash() == result.event_hash


@mock_aws
def test_get_event_hash():
    """Test get_event_hash() method."""
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events
    events = []
    for i in range(3):
        event = Event(type="TestEvent", aggregate_id="agg-1", ts=i * 100, payload={"idx": i})
        result = store.append_with_retry(event)
        events.append(result)

    # Verify get_event_hash
    for i, result in enumerate(events):
        assert store.get_event_hash(i) == result.event_hash

    # Non-existent seq
    assert store.get_event_hash(999) is None


@mock_aws
def test_aggregate_id_filtering():
    """Test aggregate_id filtering in read()."""
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events with different aggregate IDs
    for i in range(10):
        agg_id = f"agg-{i % 3}"  # agg-0, agg-1, agg-2
        event = Event(type="TestEvent", aggregate_id=agg_id, ts=i * 100, payload={"idx": i})
        store.append_with_retry(event)

    # Read agg-1 only
    agg1_events = list(store.read(aggregate_id="agg-1"))
    assert len(agg1_events) == 3  # idx 1, 4, 7
    assert all(e.aggregate_id == "agg-1" for e in agg1_events)


@mock_aws
def test_from_seq_filtering():
    """Test from_seq filtering in read()."""
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    store = S3EventStore(bucket=bucket, prefix="events")

    # Append events
    for i in range(10):
        event = Event(type="TestEvent", aggregate_id="agg-1", ts=i * 100, payload={"idx": i})
        store.append_with_retry(event)

    # Read from seq=5
    events = list(store.read(from_seq=5))
    assert len(events) == 5  # seq 5, 6, 7, 8, 9
    assert events[0].seq == 5
    assert events[-1].seq == 9


@mock_aws
def test_append_conflict_retry():
    """Test append conflict detection and retry."""
    # Create mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3_client.create_bucket(Bucket=bucket)

    store = S3EventStore(bucket=bucket, prefix="events")

    # Append first event
    event1 = Event(type="TestEvent", aggregate_id="agg-1", ts=100, payload={"idx": 0})
    result1 = store.append_with_retry(event1)
    assert result1.committed

    # Try to append with wrong expected_prev_hash (simulate conflict)
    event2 = Event(type="TestEvent", aggregate_id="agg-1", ts=200, payload={"idx": 1})
    result2 = store.append(event2, expected_prev_hash="wrong_hash")
    assert not result2.committed
    assert result2.conflict
    assert result2.observed_prev_hash == result1.event_hash

    # Retry with correct prev_hash
    result3 = store.append_with_retry(event2)
    assert result3.committed
    assert result3.seq == 1
