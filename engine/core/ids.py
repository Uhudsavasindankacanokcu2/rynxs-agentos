"""
Stable identifier generation.

Provides deterministic ID generation without randomness.
"""

import hashlib


def stable_id(*parts: str) -> str:
    """
    Generate stable ID derived from inputs (no randomness).

    Useful for deterministic aggregate ids, event ids, etc.

    Args:
        *parts: String parts to combine into ID

    Returns:
        SHA-256 hash as hex string

    Example:
        stable_id("agent", "alpha", "1") -> "a3f2..."
    """
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
