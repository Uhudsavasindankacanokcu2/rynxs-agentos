"""
Reducer handlers for deterministic operator state.

All handlers are pure and deterministic.
"""

from typing import Dict, Any

from engine.core import Event
from engine.core.state import UniverseState
from engine.core.canonical import canonical_json_str, canonicalize
from engine.core.ids import stable_id


UNIVERSE_AGG_ID = "universe"


def register_handlers(reducer) -> None:
    reducer.register("AgentObserved", on_agent_observed)
    reducer.register("ActionsDecided", on_actions_decided)
    reducer.register("ActionApplied", on_action_applied)
    reducer.register("ActionFailed", on_action_failed)


def _load_state(cur) -> UniverseState:
    if isinstance(cur, UniverseState):
        return cur
    if isinstance(cur, dict):
        return UniverseState.from_dict(cur)
    return UniverseState.initial()


def _store_state(state: UniverseState) -> Dict[str, Any]:
    return state.to_dict()


def _action_fingerprint(action_dict: Dict[str, Any]) -> str:
    params = canonicalize(action_dict.get("params", {}))
    params_json = canonical_json_str(params)
    return stable_id(action_dict.get("action_type", ""), action_dict.get("target", ""), params_json)


def on_agent_observed(cur, ev: Event) -> Dict[str, Any]:
    state = _load_state(cur)

    payload = ev.payload or {}
    agent_id = ev.aggregate_id

    agent_model = {
        "name": payload.get("name"),
        "namespace": payload.get("namespace"),
        "spec_hash": payload.get("spec_hash"),
        "spec": payload.get("spec"),
        "labels": payload.get("labels", {}),
    }

    agents = dict(state.agents)
    agents[agent_id] = agent_model

    last_seen = dict(state.last_seen_spec_hash)
    last_seen[agent_id] = payload.get("spec_hash", "")

    next_state = UniverseState(
        agents=agents,
        last_seen_spec_hash=last_seen,
        desired=state.desired,
        applied=state.applied,
        failures=state.failures,
    )
    return _store_state(next_state)


def on_actions_decided(cur, ev: Event) -> Dict[str, Any]:
    state = _load_state(cur)
    payload = ev.payload or {}

    agent_id = payload.get("agent_id") or ev.aggregate_id
    actions = payload.get("actions", [])
    actions_hash = payload.get("actions_hash")
    trigger_event_hash = payload.get("trigger_event_hash")
    trigger_event_type = payload.get("trigger_event_type")
    trigger_spec_hash = payload.get("trigger_spec_hash")
    trigger_event_seq = payload.get("trigger_event_seq")

    action_map = {}
    for a in actions:
        action_id = _action_fingerprint(a)
        action_map[action_id] = {
            "action_type": a.get("action_type"),
            "target": a.get("target"),
            "fingerprint": action_id,
        }

    desired = dict(state.desired)
    desired[agent_id] = {
        "actions": action_map,
        "actions_hash": actions_hash,
        "trigger_event_hash": trigger_event_hash,
        "trigger_event_type": trigger_event_type,
        "trigger_spec_hash": trigger_spec_hash,
        "trigger_event_seq": trigger_event_seq,
    }

    next_state = UniverseState(
        agents=state.agents,
        last_seen_spec_hash=state.last_seen_spec_hash,
        desired=desired,
        applied=state.applied,
        failures=state.failures,
    )
    return _store_state(next_state)


def on_action_applied(cur, ev: Event) -> Dict[str, Any]:
    state = _load_state(cur)
    payload = ev.payload or {}

    action_id = payload.get("action_id")
    if not action_id:
        return _store_state(state)

    applied = dict(state.applied)
    applied[action_id] = {
        "action_type": payload.get("action_type"),
        "target": payload.get("target"),
        "result_code": payload.get("result_code", "OK"),
        "applied_seq": ev.seq,
    }

    next_state = UniverseState(
        agents=state.agents,
        last_seen_spec_hash=state.last_seen_spec_hash,
        desired=state.desired,
        applied=applied,
        failures=state.failures,
    )
    return _store_state(next_state)


def on_action_failed(cur, ev: Event) -> Dict[str, Any]:
    state = _load_state(cur)
    payload = ev.payload or {}

    action_id = payload.get("action_id")
    error = payload.get("error") or {}

    failures = list(state.failures)
    failures.append(
        {
            "action_id": action_id,
            "result_code": payload.get("result_code") or error.get("code"),
            "error_code": error.get("code"),
            "error_type": error.get("type"),
            "error_status": error.get("status"),
            "error_reason": error.get("reason"),
            "failed_seq": ev.seq,
        }
    )

    next_state = UniverseState(
        agents=state.agents,
        last_seen_spec_hash=state.last_seen_spec_hash,
        desired=state.desired,
        applied=state.applied,
        failures=failures,
    )
    return _store_state(next_state)
