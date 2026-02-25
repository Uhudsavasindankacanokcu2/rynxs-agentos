"""
Exception types for deterministic execution engine.
"""


class DeterminismError(Exception):
    """Raised when determinism guarantee is violated."""
    pass


class InvalidTransitionError(Exception):
    """Raised when event handler is not registered or transition is invalid."""
    pass


class IntegrityError(Exception):
    """Raised when hash chain or signature verification fails."""
    pass


class EventStoreError(Exception):
    """Raised when event store operations fail."""
    pass
