"""
Deterministic clock implementation.

Provides monotonic time source without system time dependencies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeterministicClock:
    """
    Deterministic time source.

    In production: caller provides ts (monotonic integer).
    In tests: you can increment manually.

    This ensures replay produces identical timestamps.
    """
    current: int = 0

    def now(self) -> int:
        """Get current timestamp without advancing."""
        return self.current

    def tick(self, step: int = 1) -> "DeterministicClock":
        """
        Advance clock by step and return new clock instance.

        Since DeterministicClock is immutable, this returns a new instance.
        """
        return DeterministicClock(self.current + step)
