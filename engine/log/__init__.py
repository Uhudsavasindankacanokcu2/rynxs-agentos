"""
Event storage and integrity verification.

This module provides:
- EventStore: Abstract interface for event persistence
- FileEventStore: File-based append-only storage (JSONL)
- Integrity: Hash chain verification
"""

from .store import EventStore, AppendResult
from .file_store import FileEventStore
from .integrity import ZERO_HASH, hash_event, chain_record

__all__ = [
    "EventStore",
    "AppendResult",
    "FileEventStore",
    "ZERO_HASH",
    "hash_event",
    "chain_record",
]
