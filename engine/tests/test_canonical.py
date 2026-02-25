"""
Tests for canonical serialization.

Critical: These tests verify determinism guarantees.
"""

from engine.core.canonical import canonicalize, canonical_json_bytes, canonical_json_str


def test_canonicalize_dict_key_order():
    """Dict key order must not affect canonical output."""
    d1 = {"z": 1, "a": 2, "m": 3}
    d2 = {"a": 2, "m": 3, "z": 1}

    assert canonicalize(d1) == canonicalize(d2)


def test_canonicalize_nested():
    """Nested structures must be canonicalized recursively."""
    obj = {
        "outer": {
            "z": [3, 1, 2],
            "a": {"nested": True}
        }
    }

    canon = canonicalize(obj)

    # Keys sorted at each level
    assert list(canon.keys()) == ["outer"]
    assert list(canon["outer"].keys()) == ["a", "z"]


def test_canonical_json_bytes_determinism():
    """Same object must produce identical bytes."""
    obj = {"b": 2, "a": 1, "c": {"x": 10, "y": 20}}

    b1 = canonical_json_bytes(obj)
    b2 = canonical_json_bytes(obj)

    assert b1 == b2
    assert isinstance(b1, bytes)


def test_canonical_json_str_determinism():
    """Same object must produce identical string."""
    obj = {"b": 2, "a": 1}

    s1 = canonical_json_str(obj)
    s2 = canonical_json_str(obj)

    assert s1 == s2
    assert s1 == '{"a":1,"b":2}'  # Keys sorted, no whitespace


def test_canonical_handles_unicode():
    """Unicode strings must be handled consistently."""
    obj = {"key": "日本語"}

    s1 = canonical_json_str(obj)
    s2 = canonical_json_str(obj)

    assert s1 == s2
    assert "日本語" in s1  # ensure_ascii=False preserves unicode
