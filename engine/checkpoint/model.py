"""
Checkpoint model for signed state snapshots.

A checkpoint captures:
- State at specific event index
- Hash chain binding
- Cryptographic signature
- Deterministic serialization
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json


@dataclass
class Checkpoint:
    """
    Immutable checkpoint record.

    Fields:
        version: Format version (currently 1)
        event_index: Last applied event sequence number
        event_hash: Hash of event at event_index (from hash chain)
        state_hash: SHA-256 of canonical state bytes
        state_bytes: Canonical serialized state (base64)
        created_at_logical: Logical clock timestamp
        pubkey_id: SHA-256 hash of public key (first 16 chars)
        signature: Ed25519 signature (base64)
        meta: Optional metadata (preserve-unknown)
    """
    version: int
    event_index: int
    event_hash: str
    state_hash: str
    state_bytes: str  # base64-encoded canonical state
    created_at_logical: int
    pubkey_id: str
    signature: str  # base64-encoded Ed25519 signature
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize checkpoint to dict for JSON storage.

        Returns canonical representation suitable for signature.
        """
        return {
            "version": self.version,
            "event_index": self.event_index,
            "event_hash": self.event_hash,
            "state_hash": self.state_hash,
            "state_bytes": self.state_bytes,
            "created_at_logical": self.created_at_logical,
            "pubkey_id": self.pubkey_id,
            "signature": self.signature,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """Deserialize checkpoint from dict."""
        return cls(
            version=data["version"],
            event_index=data["event_index"],
            event_hash=data["event_hash"],
            state_hash=data["state_hash"],
            state_bytes=data["state_bytes"],
            created_at_logical=data["created_at_logical"],
            pubkey_id=data["pubkey_id"],
            signature=data["signature"],
            meta=data.get("meta", {}),
        )

    def to_json(self) -> str:
        """Serialize to JSON string (for file storage)."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Checkpoint":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def signing_payload(self) -> Dict[str, Any]:
        """
        Get payload for signing (excludes signature field).

        This is the canonical representation that gets signed.
        """
        return {
            "version": self.version,
            "event_index": self.event_index,
            "event_hash": self.event_hash,
            "state_hash": self.state_hash,
            "created_at_logical": self.created_at_logical,
            "pubkey_id": self.pubkey_id,
        }
