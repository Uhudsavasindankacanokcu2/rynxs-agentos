"""
Checkpoint system for signed state snapshots.

Provides:
- Checkpoint model with canonical serialization
- Ed25519 signing and verification
- Deterministic state snapshots
- Checkpoint storage management
- Fast replay from checkpoints
"""

from .model import Checkpoint
from .snapshot import (
    serialize_state,
    compute_state_hash,
    state_to_base64,
    state_from_base64,
)
from .signer import SigningKey, VerifyingKey, ensure_keypair
from .verify import verify_checkpoint, verify_signature, verify_full, VerificationResult
from .store import CheckpointStore

__all__ = [
    "Checkpoint",
    "serialize_state",
    "compute_state_hash",
    "state_to_base64",
    "state_from_base64",
    "SigningKey",
    "VerifyingKey",
    "ensure_keypair",
    "verify_checkpoint",
    "verify_signature",
    "verify_full",
    "VerificationResult",
    "CheckpointStore",
]
