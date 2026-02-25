"""
Canonical serialization for deterministic hashing.

This module is the heart of determinism. All state and event serialization
must go through these functions to ensure identical output across platforms.
"""

import json
from typing import Any, Dict, List


def canonicalize(obj: Any) -> Any:
    """
    Convert arbitrary nested dict/list to canonical form.

    Rules:
    - dict keys sorted alphabetically
    - tuples converted to lists
    - recursive normalization

    This ensures identical structure regardless of input order.
    """
    if isinstance(obj, dict):
        return {k: canonicalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [canonicalize(x) for x in obj]
    return obj


def canonical_json_bytes(obj: Any) -> bytes:
    """
    Deterministic JSON bytes for hashing.

    Guarantees:
    - sort_keys=True (secondary safety)
    - separators remove whitespace
    - ensure_ascii=False keeps UTF-8 stable
    - canonical preprocessing via canonicalize()

    Returns:
        UTF-8 encoded JSON bytes
    """
    canon = canonicalize(obj)
    s = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")


def canonical_json_str(obj: Any) -> str:
    """
    Deterministic JSON string (for display or storage).

    Same guarantees as canonical_json_bytes but returns string.
    """
    return canonical_json_bytes(obj).decode("utf-8")
