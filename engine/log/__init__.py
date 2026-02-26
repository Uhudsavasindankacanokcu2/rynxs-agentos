"""
Event storage and integrity verification.

This module provides:
- EventStore: Abstract interface for event persistence
- FileEventStore: File-based append-only storage (JSONL)
- S3EventStore: S3-based append-only storage (one object per event)
- Integrity: Hash chain verification
"""

from .store import EventStore, AppendResult
from .file_store import FileEventStore
from .integrity import ZERO_HASH, hash_event, chain_record

# S3EventStore is optional (requires boto3)
try:
    from .s3_store import S3EventStore

    __all__ = [
        "EventStore",
        "AppendResult",
        "FileEventStore",
        "S3EventStore",
        "ZERO_HASH",
        "hash_event",
        "chain_record",
    ]
except ImportError:
    __all__ = [
        "EventStore",
        "AppendResult",
        "FileEventStore",
        "ZERO_HASH",
        "hash_event",
        "chain_record",
    ]
