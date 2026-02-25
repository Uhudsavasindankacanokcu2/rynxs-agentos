"""
Replay system for deterministic state reconstruction.

Replay applies reducer to event stream to reconstruct state.
Must be 100% deterministic: same events -> same state.
"""

from .runner import ReplayResult, replay

__all__ = [
    "ReplayResult",
    "replay",
]
