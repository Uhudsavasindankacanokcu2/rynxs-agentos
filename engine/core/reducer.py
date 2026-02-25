"""
Reducer: Pure state transition functions.

The reducer is the heart of deterministic execution. It must be:
- Pure (no side effects, no I/O)
- Deterministic (same input -> same output)
- Idempotent (applying same event twice is safe)
"""

from typing import Callable, Dict, Any
from .events import Event
from .state import State
from .errors import InvalidTransitionError

# Handler signature: (current_aggregate_state, event) -> new_aggregate_state
Handler = Callable[[Any, Event], Any]


class Reducer:
    """
    Registry of event handlers for state transitions.

    Usage:
        reducer = Reducer()
        reducer.register("AgentCreated", handle_agent_created)
        new_state = reducer.apply(state, event)
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}

    def register(self, event_type: str, handler: Handler) -> None:
        """
        Register event handler.

        Args:
            event_type: Event type string
            handler: Pure function (current_agg_state, event) -> new_agg_state
        """
        self._handlers[event_type] = handler

    def apply(self, state: State, event: Event) -> State:
        """
        Apply event to state using registered handler.

        Args:
            state: Current state
            event: Event to apply

        Returns:
            New state with event applied

        Raises:
            InvalidTransitionError: If no handler registered for event type
        """
        if event.type not in self._handlers:
            raise InvalidTransitionError(f"No handler for event type: {event.type}")

        current = state.get_agg(event.aggregate_id)
        new_agg_state = self._handlers[event.type](current, event)
        return state.with_agg(event.aggregate_id, new_agg_state)
