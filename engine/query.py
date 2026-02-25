"""
Deterministic query helpers for engine state.
"""

from typing import Dict, Any, List, Optional
from .core.state import State, UniverseState

DEFAULT_UNIVERSE_AGG_ID = "universe"


def _universe_state(state: State, universe_id: str = DEFAULT_UNIVERSE_AGG_ID) -> UniverseState:
    agg = state.get_agg(universe_id)
    if isinstance(agg, UniverseState):
        return agg
    if isinstance(agg, dict):
        return UniverseState.from_dict(agg)
    return UniverseState.initial()


def list_agents(state: State, universe_id: str = DEFAULT_UNIVERSE_AGG_ID) -> List[str]:
    u = _universe_state(state, universe_id)
    return sorted(u.agents.keys())


def resolve_agent_id(
    state: State, agent_ref: str, universe_id: str = DEFAULT_UNIVERSE_AGG_ID
) -> Optional[str]:
    """
    Resolve agent reference to full agent_id.

    Accepts:
    - full aggregate id (namespace/name)
    - bare name (search by agent.name)
    """
    if "/" in agent_ref:
        return agent_ref

    u = _universe_state(state, universe_id)
    for agent_id, model in u.agents.items():
        if model.get("name") == agent_ref:
            return agent_id
    return None


def get_agent_state(
    state: State, agent_id: str, universe_id: str = DEFAULT_UNIVERSE_AGG_ID
) -> Optional[Dict[str, Any]]:
    u = _universe_state(state, universe_id)
    return u.agents.get(agent_id)


def get_drift(
    state: State, agent_id: str, universe_id: str = DEFAULT_UNIVERSE_AGG_ID
) -> Dict[str, Any]:
    u = _universe_state(state, universe_id)
    desired_entry = u.desired.get(agent_id, {})
    desired_actions = set((desired_entry.get("actions") or {}).keys())
    applied_actions = set(u.applied.keys())

    missing = sorted(desired_actions - applied_actions)
    extra = sorted(applied_actions - desired_actions)

    return {
        "actions_hash": desired_entry.get("actions_hash"),
        "trigger_event_hash": desired_entry.get("trigger_event_hash"),
        "trigger_event_type": desired_entry.get("trigger_event_type"),
        "trigger_spec_hash": desired_entry.get("trigger_spec_hash"),
        "trigger_event_seq": desired_entry.get("trigger_event_seq"),
        "desired_action_ids": sorted(desired_actions),
        "applied_action_ids": sorted(applied_actions & desired_actions),
        "missing_action_ids": missing,
        "extra_action_ids": extra,
    }


def get_failures(
    state: State,
    agent_id: str,
    last_n: int = 20,
    universe_id: str = DEFAULT_UNIVERSE_AGG_ID,
) -> List[Dict[str, Any]]:
    u = _universe_state(state, universe_id)
    desired_actions = set((u.desired.get(agent_id, {}).get("actions") or {}).keys())

    filtered = []
    for f in u.failures:
        if f.get("action_id") in desired_actions:
            filtered.append(f)

    return filtered[-last_n:]
