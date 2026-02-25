"""
Hash chain integrity verification.

Implements tamper-evident logging using cryptographic hash chains.
Each event includes hash of previous event, forming immutable chain.
"""

import hashlib
from typing import Dict, Any
from ..core.canonical import canonical_json_bytes
from ..core.events import Event

ZERO_HASH = "0" * 64


def _event_dict_for_hash(event: Event) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "type": event.type,
        "aggregate_id": event.aggregate_id,
        "seq": event.seq,
        "ts": event.ts,
        "payload": event.payload,
    }

    meta = event.meta if event.meta is not None else None
    if event.hash_version == "v2":
        data["hash_version"] = "v2"
        if meta:
            data["meta"] = meta
    else:
        data["meta"] = event.meta

    return data


def hash_event(prev_hash: str, event: Event) -> str:
    """
    Compute hash of event chained to previous hash.

    Hash input: prev_hash + canonical_json(event_data)

    Args:
        prev_hash: Hash of previous event (or ZERO_HASH for genesis)
        event: Event to hash

    Returns:
        SHA-256 hash as hex string
    """
    # Hash only canonical event fields (seq included once assigned)
    data = _event_dict_for_hash(event)
    b = prev_hash.encode("utf-8") + canonical_json_bytes(data)
    return hashlib.sha256(b).hexdigest()


def chain_record(prev_hash: str, event: Event) -> Dict[str, Any]:
    """
    Create hash chain record for storage.

    Record includes:
    - prev_hash: Hash of previous event
    - event_hash: Hash of this event
    - event: Full event data

    Args:
        prev_hash: Previous event hash
        event: Event to record

    Returns:
        Dict ready for JSONL serialization
    """
    h = hash_event(prev_hash, event)
    return {
        "prev_hash": prev_hash,
        "event_hash": h,
        "event": _event_dict_for_hash(event),
    }
