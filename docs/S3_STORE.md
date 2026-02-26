# S3 Event Store

S3-based event storage for rynxs operator with deterministic ordering, hash-chain integrity, and HA compatibility.

## Overview

`S3EventStore` stores events as individual S3 objects, providing:

- **Scalable Storage**: Supports millions of events without file size limits
- **HA Compatible**: No single-file locking (unlike FileEventStore with RWO PVC)
- **Parallel Reads**: Each event is a separate object, enabling range/partial downloads
- **Strong Consistency**: AWS S3 guarantees strong read-after-write consistency (as of Dec 2020)
- **Hash-Chain Integrity**: Same tamper-evident guarantees as FileEventStore

## Key Naming Scheme

Events are stored with zero-padded sequence numbers to ensure lexicographic order equals numeric order:

```
s3://{bucket}/{prefix}/{seq:010d}.json
```

**Example**:
```
s3://rynxs-events/events/0000000000.json
s3://rynxs-events/events/0000000001.json
s3://rynxs-events/events/0000000042.json
```

**Why zero-padding?**
S3 list_objects_v2 returns keys in lexicographic order. Without zero-padding, "10" would sort before "2". With 10-digit padding (supports up to 9,999,999,999 events), lexicographic order = numeric seq order.

## Object Format

Each event object contains a hash-chain record (same format as FileEventStore):

```json
{
  "prev_hash": "abc123...",
  "event_hash": "def456...",
  "event": {
    "type": "AgentObserved",
    "aggregate_id": "agent-default-example",
    "seq": 42,
    "ts": 1234567890,
    "payload": {...},
    "meta": {...}
  }
}
```

**Fields**:
- `prev_hash`: Hash of previous event (or `"0"*64` for genesis event at seq=0)
- `event_hash`: SHA-256 hash of `prev_hash + canonical_json(event)`
- `event`: Full event data (same as FileEventStore)

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `EVENT_STORE_TYPE` | Store type (`file` or `s3`) | `file` | No |
| `S3_BUCKET` | S3 bucket name | `rynxs-events` | Yes (if `s3`) |
| `S3_PREFIX` | Key prefix for events | `events` | No |
| `S3_ENDPOINT` | S3 endpoint URL (for MinIO) | (none) | No |
| `S3_REGION` | AWS region | `us-east-1` | No |
| `AWS_ACCESS_KEY_ID` | S3 credentials | (from env) | Yes |
| `AWS_SECRET_ACCESS_KEY` | S3 credentials | (from env) | Yes |
| `RYNXS_S3_USE_HEAD` | Enable head cache | `true` | No |
| `RYNXS_S3_HEAD_KEY` | Head object key | `<prefix>/_head.json` | No |

### Helm Values (operator chart)

Already configured in `helm/rynxs/values.yaml`:

```yaml
logSink:
  type: s3  # Change from "file" to "s3"
  s3:
    enabled: true
    endpoint: "minio-service.rynxs.svc.cluster.local:9000"  # For MinIO
    bucket: "rynxs-events"
    region: "us-east-1"
    accessKeySecret: "rynxs-s3-credentials"  # K8s secret name
```

See `helm/rynxs/README.md` for full deployment examples.

## Hash-Chain Validation

S3EventStore validates the hash chain during `read()`:

1. **prev_hash check**: Each event's `prev_hash` must match the previous event's `event_hash`
2. **event_hash recompute**: Recompute `event_hash` from `prev_hash + canonical_json(event)` and verify match
3. **seq continuity**: Ensure no gaps (seq must increment by 1)

**On failure**: Raises `EventStoreError` with details (seq number, expected vs actual hash).

## Pagination

S3's `list_objects_v2` API returns a maximum of 1000 keys per request. S3EventStore uses boto3's **paginator** to automatically handle continuation tokens:

```python
paginator = s3_client.get_paginator("list_objects_v2")
page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

for page in page_iterator:
    for obj in page.get("Contents", []):
        # Process each key
```

This ensures all events are read, even for logs with millions of events.

**Test coverage**: `test_t2_pagination_1000_plus_events()` verifies >1000 events.

## Performance Considerations

### Read Performance

- **Head cache**: `_head.json` stores the latest seq/hash to avoid full list scans.
- **Fallback scan**: If head is missing/invalid, the store falls back to listing all keys.

### Append Performance

- **Single PutObject**: Each append is one S3 API call (~10-50ms latency).
- **Append-only safety**: Conditional put (`If-None-Match: *`) prevents overwrites on seq collisions.
- **Conflict detection**: `expected_prev_hash` + conditional put ensures safe CAS semantics.

### Cost

- **Storage**: Standard S3 pricing (~$0.023/GB/month)
- **Requests**: PutObject (~$0.005 per 1000 requests), GetObject (~$0.0004 per 1000 requests)
- **List calls**: ListObjects charged per 1000 requests

## Comparison: FileEventStore vs S3EventStore

| Feature | FileEventStore | S3EventStore |
|---------|----------------|--------------|
| **Storage** | Single JSONL file | One object per event |
| **Scalability** | Limited by file size | Millions of events |
| **HA** | Requires RWX PVC or leader election | No file locking, HA-native |
| **Consistency** | fsync durability | S3 strong consistency |
| **Pagination** | N/A (single file) | boto3 paginator (>1000 events) |
| **Cost** | K8s PVC | S3 storage + API calls |
| **Replay speed** | Fast (single file read) | Slower (list + get per event) |

**Recommendation**: Use FileEventStore for dev/single-node, S3EventStore for production/HA.

## Usage Example

### Python

```python
from engine.log import S3EventStore
from engine.core.events import Event

# Create store (credentials from env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
store = S3EventStore(
    bucket="rynxs-events",
    prefix="events",
    endpoint_url="http://minio:9000",  # Optional, for MinIO
    region="us-east-1",
)

# Append event
event = Event(type="TestEvent", aggregate_id="agg-1", ts=100, payload={"foo": "bar"})
result = store.append_with_retry(event)
print(f"Appended seq={result.seq}, hash={result.event_hash}")

# Read events
for event in store.read():
    print(f"seq={event.seq}, type={event.type}, payload={event.payload}")
```

### Operator Deployment

1. Create S3 bucket and credentials secret:
   ```bash
   kubectl create secret generic rynxs-s3-credentials \
     --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
     --from-literal=AWS_SECRET_ACCESS_KEY=minioadmin
   ```

2. Update Helm values:
   ```yaml
   logSink:
     type: s3
     s3:
       enabled: true
       endpoint: "http://minio:9000"
       bucket: "rynxs-events"
   ```

3. Deploy operator:
   ```bash
   helm upgrade rynxs ./helm/rynxs --values values.yaml
   ```

## Testing

Unit tests with moto (S3 mock):

```bash
# Install test dependencies
pip install -e ".[dev,s3]"

# Run S3 store tests
pytest engine/tests/test_s3_store.py -v
```

**Test coverage**:
- T1: Append + Read roundtrip
- T2: Pagination (1000+ events)
- T3: Tamper detection (hash corruption)
- T4: Gap detection (missing sequence)
- T5: Bucket access errors

## Limitations & Future Work

### Current Limitations

1. **No checkpointing**: Replay always starts from seq=0 (future: S3-based checkpoint storage)
2. **No aggregate_id indexing**: Filtering by aggregate_id requires reading all events

### Future Enhancements (E2.2+)

1. **Head object hardening**: Conditional head updates with monotonic guarantees under high contention
2. **S3 Select**: Use S3 Select queries to filter events by aggregate_id (requires Parquet format)
3. **MinIO e2e tests**: Deploy MinIO in CI and run integration tests
4. **Lifecycle policies**: Auto-archive old events to Glacier (cost optimization)

## References

- [AWS S3 Strong Consistency](https://aws.amazon.com/s3/consistency/) (Dec 2020 announcement)
- [boto3 Paginator Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/paginators.html)
- [MinIO Python Client](https://min.io/docs/minio/linux/developers/python/minio-py.html)
- [S3 Key Naming Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)

## Support

For issues or questions:
- GitHub Issues: https://github.com/rynxs/rynxs-agentos/issues
- Slack: #rynxs-operator (coming soon)
