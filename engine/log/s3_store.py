"""
S3-based event store using one-object-per-event pattern.

Each event is stored as a separate S3 object with key: {prefix}/{seq:010d}.json
Body format: {"prev_hash": "...", "event_hash": "...", "event": {...}}

This provides:
- Scalable storage (millions of events)
- Parallel reads (range/partial downloads)
- Strong consistency (AWS S3 guarantee as of Dec 2020)
- HA-compatible (no single file lock)
"""

import json
import os
from typing import Iterator, Optional, Tuple

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None  # type: ignore
    BotoCoreError = Exception  # type: ignore
    ClientError = Exception  # type: ignore

from ..core.canonical import canonical_json_str
from ..core.errors import EventStoreError
from ..core.events import Event
from .integrity import ZERO_HASH, chain_record, hash_event
from .store import AppendResult, EventStore


class S3EventStore(EventStore):
    """
    S3-based append-only event store.

    Storage format: One JSON object per event
    Object key: {prefix}/{seq:010d}.json
    Body: {"prev_hash": "...", "event_hash": "...", "event": {...}}

    Guarantees:
    - Append-only (no mutations)
    - Deterministic ordering (lexicographic key order = numeric seq order)
    - Hash chain integrity
    - Strong consistency (AWS S3 as of Dec 2020)

    Key naming: seq zero-padded to 10 digits ensures lex order = numeric order.
    Example: 0000000000.json, 0000000001.json, ...

    Paginator: boto3 list_objects_v2 returns max 1000 keys per call.
    Use paginator to iterate all keys.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "events",
        endpoint_url: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        """
        Initialize S3 event store.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for events (default: "events")
            endpoint_url: S3 endpoint URL (for MinIO, localstack, etc.)
            region: AWS region (default: us-east-1)

        Raises:
            EventStoreError: If boto3 not installed or S3 client creation fails
        """
        if boto3 is None:
            raise EventStoreError("boto3 not installed (pip install boto3)")

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.endpoint_url = endpoint_url
        self.region = region
        self.use_head_cache = os.getenv("RYNXS_S3_USE_HEAD", "true").lower() == "true"
        self.head_key = os.getenv("RYNXS_S3_HEAD_KEY", f"{self.prefix}/_head.json")

        # Create S3 client (credentials from environment: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        try:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                region_name=region,
            )
        except Exception as e:
            raise EventStoreError(f"Failed to create S3 client: {e}") from e

        # Verify bucket exists (optional, can be disabled for performance)
        if os.getenv("RYNXS_S3_SKIP_BUCKET_CHECK", "").lower() != "true":
            try:
                self.s3_client.head_bucket(Bucket=bucket)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                raise EventStoreError(
                    f"Bucket '{bucket}' not accessible (code: {error_code})"
                ) from e

    def _key_for_seq(self, seq: int) -> str:
        """Generate S3 key for sequence number (zero-padded to 10 digits)."""
        return f"{self.prefix}/{seq:010d}.json"

    def _seq_from_key(self, key: str) -> Optional[int]:
        """Extract sequence number from S3 key."""
        if not key.startswith(self.prefix + "/"):
            return None
        basename = key[len(self.prefix) + 1 :]
        if not basename.endswith(".json"):
            return None
        seq_str = basename[:-5]  # Remove ".json"
        try:
            return int(seq_str)
        except ValueError:
            return None

    def _get_last_seq_and_hash(self) -> Tuple[int, str]:
        """
        Get last sequence number and hash from S3.

        Returns:
            (last_seq, last_hash) tuple
            (-1, ZERO_HASH) if no events exist
        """
        try:
            # Prefer head cache if enabled
            if self.use_head_cache:
                head = self._read_head()
                if head is not None:
                    return head

            # Fallback to full list (O(N))
            return self._scan_last_seq_and_hash()

        except (BotoCoreError, ClientError) as e:
            raise EventStoreError(f"Failed to get last seq/hash from S3: {e}") from e

    def _scan_last_seq_and_hash(self) -> Tuple[int, str]:
        """
        Scan all event objects to find last seq/hash.

        Returns:
            (last_seq, last_hash) tuple
            (-1, ZERO_HASH) if no events exist
        """
        paginator = self.s3_client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + "/")

        last_seq = -1
        last_key = None
        for page in page_iterator:
            if "Contents" not in page:
                continue
            for obj in page["Contents"]:
                key = obj["Key"]
                seq = self._seq_from_key(key)
                if seq is None:
                    continue
                if seq > last_seq:
                    last_seq = seq
                    last_key = key

        if last_key is None:
            return -1, ZERO_HASH

        response = self.s3_client.get_object(Bucket=self.bucket, Key=last_key)
        body = response["Body"].read().decode("utf-8")
        rec = json.loads(body)
        return rec["event"]["seq"], rec["event_hash"]

    def _read_head(self) -> Optional[Tuple[int, str]]:
        """
        Read head cache object if present.

        Returns:
            (last_seq, last_hash) or None if not found/invalid.
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=self.head_key)
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
            last_seq = int(data.get("last_seq", -1))
            last_hash = data.get("last_hash", ZERO_HASH)
            return last_seq, last_hash
        except (BotoCoreError, ClientError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _write_head(self, last_seq: int, last_hash: str) -> None:
        """
        Best-effort head update. Uses If-Match to avoid overwriting newer head.
        """
        if not self.use_head_cache:
            return
        try:
            # Read current head to compare
            response = self.s3_client.get_object(Bucket=self.bucket, Key=self.head_key)
            etag = response.get("ETag")
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
            current_seq = int(data.get("last_seq", -1))
            if current_seq >= last_seq:
                return

            payload = canonical_json_str({"last_seq": last_seq, "last_hash": last_hash})
            if etag:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.head_key,
                    Body=payload.encode("utf-8"),
                    ContentType="application/json",
                    IfMatch=etag.strip('"'),
                )
            else:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.head_key,
                    Body=payload.encode("utf-8"),
                    ContentType="application/json",
                )
        except ClientError as e:
            # Ignore precondition failures or read errors (best-effort cache)
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("PreconditionFailed", "412", "NoSuchKey"):
                return
            raise
        except (BotoCoreError, json.JSONDecodeError, ValueError, TypeError):
            return

    def _put_event_object(self, key: str, body: str) -> bool:
        """
        Put object only if it does not already exist.

        Returns:
            True if committed, False if conflict (object exists)
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
                IfNoneMatch="*",
            )
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("PreconditionFailed", "412"):
                return False
            raise
    def append(self, event: Event, expected_prev_hash: Optional[str] = None) -> AppendResult:
        """
        Append event to S3 with hash chain.

        Args:
            event: Event to append (seq will be assigned)
            expected_prev_hash: Expected previous hash (for CAS retry)

        Returns:
            AppendResult with commit/conflict info

        Raises:
            EventStoreError: If append fails
        """
        try:
            # Get last seq and hash (head cache or scan)
            last_seq, last_hash = self._get_last_seq_and_hash()

            # Check for conflict
            if expected_prev_hash is not None and expected_prev_hash != last_hash:
                return AppendResult(
                    event=event,
                    seq=None,
                    event_hash=None,
                    prev_hash=None,
                    committed=False,
                    conflict=True,
                    observed_prev_hash=last_hash,
                )

            # Assign seq and compute hash
            seq = last_seq + 1

            # Handle hash_version (same logic as FileEventStore)
            hash_version = event.hash_version
            env_hash_version = os.getenv("RYNXS_HASH_VERSION")
            if env_hash_version:
                env_val = env_hash_version.strip().lower()
                if env_val not in ("v1", "v2"):
                    raise EventStoreError(f"unsupported hash version: {env_hash_version}")
                if hash_version and env_val != hash_version:
                    raise EventStoreError(
                        f"hash version mismatch: env={env_val} event={hash_version}"
                    )
                if env_val == "v2":
                    hash_version = "v2"
                elif env_val == "v1":
                    hash_version = None
            elif not hash_version:
                hash_version = None

            e2 = Event(
                type=event.type,
                aggregate_id=event.aggregate_id,
                seq=seq,
                ts=event.ts,
                payload=event.payload,
                meta=event.meta,
                hash_version=hash_version,
            )

            # Create hash chain record
            rec = chain_record(last_hash, e2)
            body = canonical_json_str(rec)

            # Write to S3 (append-only, no overwrite)
            key = self._key_for_seq(seq)
            committed = self._put_event_object(key, body)
            if not committed:
                # Object already exists, treat as conflict; refresh observed prev hash
                observed_last_seq, observed_last_hash = self._scan_last_seq_and_hash()
                return AppendResult(
                    event=event,
                    seq=None,
                    event_hash=None,
                    prev_hash=None,
                    committed=False,
                    conflict=True,
                    observed_prev_hash=observed_last_hash,
                )

            # Best-effort head update
            self._write_head(seq, rec.get("event_hash"))

            return AppendResult(
                event=e2,
                seq=seq,
                event_hash=rec.get("event_hash"),
                prev_hash=last_hash,
                committed=True,
                conflict=False,
                observed_prev_hash=last_hash,
            )

        except (BotoCoreError, ClientError) as e:
            raise EventStoreError(f"Failed to append event to S3: {e}") from e

    def read(
        self, aggregate_id: Optional[str] = None, from_seq: int = 0
    ) -> Iterator[Event]:
        """
        Read events from S3 with hash chain validation.

        Args:
            aggregate_id: Filter by aggregate ID (None = all)
            from_seq: Start from this sequence (inclusive)

        Yields:
            Events in sequence order

        Raises:
            EventStoreError: If read fails or hash chain is invalid
        """
        try:
            # List all event objects (paginator handles >1000 keys)
            paginator = self.s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + "/")

            # Collect all keys and sort by seq (paranoia: S3 lex order should already be sorted)
            keys = []
            for page in page_iterator:
                if "Contents" not in page:
                    continue
                for obj in page["Contents"]:
                    key = obj["Key"]
                    seq = self._seq_from_key(key)
                    if seq is not None:
                        keys.append((seq, key))

            keys.sort()  # Ensure seq order (lex order should already be correct)

            # Read events and validate hash chain
            prev_hash = ZERO_HASH
            prev_seq = -1

            for seq, key in keys:
                # Apply from_seq filter
                if seq < from_seq:
                    # Still need to track prev_hash for chain validation
                    response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                    body = response["Body"].read().decode("utf-8")
                    rec = json.loads(body)
                    prev_hash = rec["event_hash"]
                    prev_seq = seq
                    continue

                # Read event
                response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                body = response["Body"].read().decode("utf-8")
                rec = json.loads(body)

                # Validate hash chain
                if rec["prev_hash"] != prev_hash:
                    raise EventStoreError(
                        f"Hash chain broken at seq={seq}: "
                        f"expected prev_hash={prev_hash}, got {rec['prev_hash']}"
                    )

                # Validate seq continuity
                if prev_seq >= 0 and seq != prev_seq + 1:
                    raise EventStoreError(
                        f"Sequence gap detected: prev_seq={prev_seq}, current_seq={seq}"
                    )

                # Recompute and validate event_hash
                ev_data = rec["event"]
                event_obj = Event(
                    type=ev_data["type"],
                    aggregate_id=ev_data["aggregate_id"],
                    seq=ev_data["seq"],
                    ts=ev_data["ts"],
                    payload=ev_data.get("payload", {}),
                    meta=ev_data.get("meta", {}),
                    hash_version=ev_data.get("hash_version"),
                )
                recomputed_hash = hash_event(prev_hash, event_obj)
                if recomputed_hash != rec["event_hash"]:
                    raise EventStoreError(
                        f"Hash mismatch at seq={seq}: "
                        f"expected {rec['event_hash']}, recomputed {recomputed_hash}"
                    )

                # Apply aggregate_id filter
                if aggregate_id is not None and event_obj.aggregate_id != aggregate_id:
                    prev_hash = rec["event_hash"]
                    prev_seq = seq
                    continue

                # Yield event
                prev_hash = rec["event_hash"]
                prev_seq = seq
                yield event_obj

        except (BotoCoreError, ClientError) as e:
            raise EventStoreError(f"Failed to read events from S3: {e}") from e

    def get_last_hash(self) -> Optional[str]:
        """
        Return last event hash if available.

        Returns:
            Last event hash or None if no events exist
        """
        try:
            _, last_hash = self._get_last_seq_and_hash()
            return last_hash if last_hash != ZERO_HASH else None
        except EventStoreError:
            return None

    def get_event_hash(self, seq: int) -> Optional[str]:
        """
        Return event_hash for a given sequence number.

        Args:
            seq: Sequence number

        Returns:
            Event hash or None if not found
        """
        try:
            key = self._key_for_seq(seq)
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            rec = json.loads(body)
            return rec.get("event_hash")
        except (BotoCoreError, ClientError):
            return None
