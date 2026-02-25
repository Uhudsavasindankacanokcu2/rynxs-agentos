"""
Deterministic state snapshot utilities.

Ensures same state always produces same bytes.
"""

import hashlib
import base64
from typing import Any
from ..core.state import State
from ..core.canonical import canonical_json_bytes


def serialize_state(state: State) -> bytes:
    """
    Serialize state to deterministic bytes.

    Uses canonical JSON serialization to ensure:
    - Same state always produces same bytes
    - No dict ordering issues
    - No whitespace variance
    - UTF-8 stable

    Args:
        state: State to serialize

    Returns:
        Canonical bytes representation
    """
    # Convert state to dict
    state_dict = {
        "version": state.version,
        "aggregates": state.aggregates,
    }

    # Use canonical serialization
    return canonical_json_bytes(state_dict)


def compute_state_hash(state: State) -> str:
    """
    Compute SHA-256 hash of state.

    Args:
        state: State to hash

    Returns:
        Hex string (64 characters)
    """
    state_bytes = serialize_state(state)
    return hashlib.sha256(state_bytes).hexdigest()


def state_to_base64(state: State) -> str:
    """
    Serialize state to base64 string.

    Args:
        state: State to serialize

    Returns:
        Base64-encoded canonical state bytes
    """
    state_bytes = serialize_state(state)
    return base64.b64encode(state_bytes).decode("ascii")


def state_from_base64(b64_str: str) -> State:
    """
    Deserialize state from base64 string.

    Args:
        b64_str: Base64-encoded state bytes

    Returns:
        Reconstructed State object
    """
    import json

    state_bytes = base64.b64decode(b64_str)
    state_dict = json.loads(state_bytes)

    return State(
        version=state_dict["version"],
        aggregates=state_dict["aggregates"],
    )
