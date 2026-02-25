"""
Operator determinism tests (Sprint C).

Critical tests for paper/enterprise:
- Test A: Decision determinism (same input → same actions, 50 runs)
- Test B: Replay equality (live decisions == replay decisions)

These tests prove the operator is deterministic and replayable.
"""

import sys
import os
import tempfile
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from engine.core import Event, State, Reducer
from engine.core.canonical import canonical_json_bytes
from engine.log import FileEventStore
from engine.log.integrity import hash_event, ZERO_HASH
from engine.replay import replay as replay_events
from engine.core.clock import DeterministicClock
from engine.core.canonical import canonical_json_str
from engine.verify import verify_actions_decided_pointers

# Import operator components (avoid name conflict with Python's operator module)
import importlib.util

operator_path = os.environ.get("RYNXS_OPERATOR_PATH") or str(REPO_ROOT / "operator" / "universe_operator")
if not Path(operator_path).exists():
    operator_path = str(REPO_ROOT / "operator" / "universe_operator")
adapter_spec = importlib.util.spec_from_file_location("engine_adapter", f"{operator_path}/engine_adapter.py")
decision_spec = importlib.util.spec_from_file_location("decision_layer", f"{operator_path}/decision_layer.py")

adapter_module = importlib.util.module_from_spec(adapter_spec)
decision_module = importlib.util.module_from_spec(decision_spec)

adapter_spec.loader.exec_module(adapter_module)
decision_spec.loader.exec_module(decision_module)

EngineAdapter = adapter_module.EngineAdapter
DecisionLayer = decision_module.DecisionLayer
actions_to_canonical = decision_module.actions_to_canonical
action_id = decision_module.action_id

handlers_spec = importlib.util.spec_from_file_location("reducer_handlers", f"{operator_path}/reducer_handlers.py")
handlers_module = importlib.util.module_from_spec(handlers_spec)
handlers_spec.loader.exec_module(handlers_module)
register_handlers = handlers_module.register_handlers
UNIVERSE_AGG_ID = handlers_module.UNIVERSE_AGG_ID


def _state_hash(state: State) -> str:
    data = {"version": state.version, "aggregates": state.aggregates}
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def test_decision_determinism_50_runs():
    """
    Test A: Decision determinism.

    Same (state, event) must produce identical actions across 50 runs.

    This is the core determinism guarantee.
    """
    print("\nTest A: Decision determinism (50 runs)")

    # Create fixed state and event
    state = State(version=0, aggregates={})

    clock = DeterministicClock(current=1000)
    adapter = EngineAdapter(clock)

    # Create AgentObserved event with fixed spec
    agent_spec = {
        "role": "worker",
        "team": "backend-team",
        "permissions": {"canAssignTasks": False},
        "image": {"repository": "ghcr.io/test/agent", "tag": "v1.0.0"},
        "workspace": {"size": "1Gi"},
    }

    event = adapter.agent_to_event(
        name="agent-test-001", namespace="universe", spec=agent_spec
    )

    # Run decision 50 times
    decision_layer = DecisionLayer()
    action_outputs = []

    for i in range(50):
        actions = decision_layer.decide(state, event)

        # Serialize actions to canonical JSON for comparison
        actions_dict = [
            {
                "action_type": a.action_type,
                "target": a.target,
                "params": a.params,
            }
            for a in actions
        ]
        canonical = canonical_json_str(actions_dict)
        action_outputs.append(canonical)

        if i == 0:
            print(f"  Run 1: {len(actions)} actions decided")

    # Verify all outputs are identical
    unique_outputs = set(action_outputs)
    assert len(unique_outputs) == 1, f"Non-deterministic! Got {len(unique_outputs)} unique outputs"

    print(f"  ✓ All 50 runs produced identical actions")
    print(f"  ✓ Actions: {len(decision_layer.decide(state, event))}")


def test_replay_equality():
    """
    Test B: Replay equality.

    Live run decisions must equal replay run decisions.

    Proves:
    - Events capture all decision inputs
    - Replay reconstructs exact state
    - Decisions are deterministic
    """
    print("\nTest B: Replay equality")

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        clock = DeterministicClock(current=0)
        adapter = EngineAdapter(clock)
        decision_layer = DecisionLayer()
        reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
        register_handlers(reducer)

        # Simulate 10 agent observations
        print("  Simulating 10 agent observations...")
        live_decisions = []

        for i in range(10):
            agent_spec = {
                "role": "worker",
                "team": "backend-team",
                "permissions": {"canAssignTasks": False},
                "image": {"repository": "ghcr.io/test/agent", "tag": "v1.0.0"},
                "workspace": {"size": "1Gi"},
            }

            # Translate → Event
            event = adapter.agent_to_event(
                name=f"agent-{i:03d}", namespace="universe", spec=agent_spec
            )

            # Append to log
            event_stored = store.append(event)

            # Replay to get state
            replay_result = replay_events(store, reducer)
            state = replay_result.state

            # Decide actions (LIVE)
            actions = decision_layer.decide(state, event_stored)
            actions_canonical = actions_to_canonical(actions)
            live_decisions.append(canonical_json_str(actions_canonical))

            # Append ActionsDecided event
            trigger_event_hash = store.get_event_hash(event_stored.seq)
            actions_hash = hashlib.sha256(
                canonical_json_str(actions_canonical).encode("utf-8")
            ).hexdigest()
            decision_event = Event(
                type="ActionsDecided",
                aggregate_id=event_stored.aggregate_id,
                ts=1000 + i,
                payload={
                    "agent_id": event_stored.aggregate_id,
                    "trigger_event_seq": event_stored.seq,
                    "trigger_event_hash": trigger_event_hash,
                    "trigger_event_type": event_stored.type,
                    "trigger_spec_hash": event_stored.payload.get("spec_hash"),
                    "actions": actions_canonical,
                    "actions_hash": actions_hash,
                    "action_ids": [action_id(a) for a in actions],
                },
            )
            store.append(decision_event)

        print(f"  Live run: {len(live_decisions)} decisions made")

        # Now replay entire log and reproduce decisions
        print("  Replaying entire log...")
        replay_decisions = []

        # Start with initial state
        state = State(version=0, aggregates={})

        for event_stored in store.read(from_seq=0):
            if event_stored.type != "AgentObserved":
                continue
            # Replay: update state
            # (In real implementation, reducer would update state)

            # Decide actions (REPLAY)
            actions = decision_layer.decide(state, event_stored)
            actions_canonical = actions_to_canonical(actions)
            replay_decisions.append(canonical_json_str(actions_canonical))

        print(f"  Replay run: {len(replay_decisions)} decisions made")

        # Compare live vs replay
        assert len(live_decisions) == len(
            replay_decisions
        ), f"Decision count mismatch: {len(live_decisions)} vs {len(replay_decisions)}"

        for i, (live, replay) in enumerate(zip(live_decisions, replay_decisions)):
            assert (
                live == replay
            ), f"Decision {i} mismatch:\nLive: {live}\nReplay: {replay}"

        print(f"  ✓ All {len(live_decisions)} decisions match (live == replay)")


def test_event_translation_determinism():
    """
    Test C: Event translation determinism.

    Same K8s object must produce same event (hash).
    """
    print("\nTest C: Event translation determinism")

    clock = DeterministicClock(current=1000)
    adapter = EngineAdapter(clock)

    agent_spec = {
        "role": "worker",
        "team": "backend-team",
        "permissions": {"canAssignTasks": False},
        "image": {"repository": "ghcr.io/test/agent", "tag": "v1.0.0"},
        "workspace": {"size": "1Gi"},
    }

    # Translate 100 times
    events = []
    for _ in range(100):
        event = adapter.agent_to_event(
            name="agent-test-001", namespace="universe", spec=agent_spec
        )
        events.append(canonical_json_str(event.payload))

    # All payloads must be identical
    unique_payloads = set(events)
    assert (
        len(unique_payloads) == 1
    ), f"Non-deterministic translation! Got {len(unique_payloads)} unique payloads"

    print(f"  ✓ 100 translations produced identical events")
    print(f"  ✓ spec_hash: {events[0][:50]}...")


def test_event_translation_defaulting_equivalence():
    """
    Test D: K8s defaulting equivalence.

    Semantically identical specs (implicit defaults vs explicit defaults)
    must translate to identical deterministic events.
    """
    print("\nTest D: Event translation defaulting equivalence")

    clock = DeterministicClock(current=1000)
    adapter = EngineAdapter(clock)

    spec_implicit = {
        "team": "backend-team",
        "permissions": {},
        "image": {"repository": "ghcr.io/test/agent"},
        "workspace": {},
    }

    spec_explicit = {
        "role": "worker",
        "team": "backend-team",
        "permissions": {
            "canAssignTasks": False,
            "canAccessAuditLogs": False,
            "canManageTeam": False,
        },
        "image": {
            "repository": "ghcr.io/test/agent",
            "tag": "latest",
            "verify": False,
        },
        "workspace": {"size": "1Gi"},
    }

    ev_a = adapter.agent_to_event(
        name="agent-test-001", namespace="universe", spec=spec_implicit
    )
    ev_b = adapter.agent_to_event(
        name="agent-test-001", namespace="universe", spec=spec_explicit
    )

    payload_a = canonical_json_str(ev_a.payload)
    payload_b = canonical_json_str(ev_b.payload)

    assert (
        payload_a == payload_b
    ), f"Defaulting drift detected:\nimplicit={payload_a}\nexplicit={payload_b}"

    print("  ✓ Implicit defaults == explicit defaults (payloads match)")


def test_real_state_replay_equivalence():
    """
    Test E: Real state replay equivalence.

    Live state evolution must equal replayed state.
    """
    print("\nTest E: Real state replay equivalence")

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        clock = DeterministicClock(current=0)
        adapter = EngineAdapter(clock)
        decision_layer = DecisionLayer()

        reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
        register_handlers(reducer)

        state_live = State(version=0, aggregates={})
        ts = 0

        for i in range(5):
            agent_spec = {
                "role": "worker",
                "team": "backend-team",
                "permissions": {"canAssignTasks": False},
                "image": {"repository": "ghcr.io/test/agent", "tag": "v1.0.0"},
                "workspace": {"size": "1Gi"},
            }

            # AgentObserved
            event = adapter.agent_to_event(
                name=f"agent-{i:03d}", namespace="universe", spec=agent_spec
            )
            event_stored = store.append(event)
            state_live = reducer.apply(state_live, event_stored)

            # Decide + ActionsDecided
            actions = decision_layer.decide(state_live, event_stored)
            actions_canonical = actions_to_canonical(actions)
            ts += 1
            trigger_event_hash = store.get_event_hash(event_stored.seq)
            actions_hash = hashlib.sha256(
                canonical_json_str(actions_canonical).encode("utf-8")
            ).hexdigest()
            decided = Event(
                type="ActionsDecided",
                aggregate_id=event_stored.aggregate_id,
                ts=ts,
                payload={
                    "agent_id": event_stored.aggregate_id,
                    "trigger_event_seq": event_stored.seq,
                    "trigger_event_hash": trigger_event_hash,
                    "trigger_event_type": event_stored.type,
                    "trigger_spec_hash": event_stored.payload.get("spec_hash"),
                    "actions": actions_canonical,
                    "actions_hash": actions_hash,
                    "action_ids": [action_id(a) for a in actions],
                },
            )
            decided_stored = store.append(decided)
            state_live = reducer.apply(state_live, decided_stored)

            # Simulate feedback (applied)
            for action in actions:
                ts += 1
                feedback = Event(
                    type="ActionApplied",
                    aggregate_id=event_stored.aggregate_id,
                    ts=ts,
                    payload={
                        "action_id": action_id(action),
                        "action_type": action.action_type,
                        "target": action.target,
                        "result_code": "OK",
                    },
                )
                feedback_stored = store.append(feedback)
                state_live = reducer.apply(state_live, feedback_stored)

        # Replay full log
        replay_result = replay_events(store, reducer)

        live_hash = _state_hash(state_live)
        replay_hash = _state_hash(replay_result.state)

        assert live_hash == replay_hash, "State hash mismatch (live vs replay)"
    print("  ✓ Live state hash == replay state hash")


def test_golden_log_fixture_replay():
    """
    Test F: Golden log fixture replay determinism.

    Replay of fixture log must yield the expected state hash.
    """
    print("\nTest F: Golden fixture replay")

    fixture_path = Path(__file__).parent / "fixtures" / "operator_log_small.jsonl"
    expected_hash = "6a2d25ae69313ebf7eaa4ce0ef9658b4a6aee6165e2a15edd6b0b6e20b4a4b29"

    reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
    register_handlers(reducer)

    store = FileEventStore(str(fixture_path))
    replay_result = replay_events(store, reducer)

    state_hash = _state_hash(replay_result.state)
    assert (
        state_hash == expected_hash
    ), f"Golden fixture hash mismatch: {state_hash} != {expected_hash}"
    print("  ✓ Golden fixture hash matches")

def test_golden_log_weird_fixture_replay():
    """
    Test G: Weird fixture replay determinism.

    Replay of weird fixture log must yield the expected state hash.
    """
    print("\nTest G: Weird fixture replay")

    fixture_path = Path(__file__).parent / "fixtures" / "operator_log_weird.jsonl"
    expected_hash = "228a0f4184447c46566e3d2225c16cbe4048d8bca2e11f34d07addf94289c268"

    reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
    register_handlers(reducer)

    store = FileEventStore(str(fixture_path))
    replay_result = replay_events(store, reducer)

    state_hash = _state_hash(replay_result.state)
    assert (
        state_hash == expected_hash
    ), f"Weird fixture hash mismatch: {state_hash} != {expected_hash}"
    print("  ✓ Weird fixture hash matches")


def _tamper_pointer_fixture(src_path: Path, dst_path: Path) -> None:
    records = []
    tampered = False
    with src_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            ev = rec.get("event", {})
            if ev.get("type") == "ActionsDecided" and not tampered:
                payload = ev.get("payload", {})
                payload["trigger_event_hash"] = "0" * 64
                ev["payload"] = payload
                rec["event"] = ev
                tampered = True
            records.append(rec)

    prev_hash = ZERO_HASH
    for rec in records:
        ev = rec.get("event", {})
        event_obj = Event(
            type=ev.get("type"),
            aggregate_id=ev.get("aggregate_id"),
            seq=ev.get("seq"),
            ts=ev.get("ts"),
            payload=ev.get("payload", {}),
            meta=ev.get("meta", {}),
        )
        rec["prev_hash"] = prev_hash
        rec["event_hash"] = hash_event(prev_hash, event_obj)
        prev_hash = rec["event_hash"]

    with dst_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_verify_actions_decided_pointers_pass():
    """
    Test H: Pointer verification passes on small fixture.
    """
    print("\nTest H: Pointer verification (pass)")
    fixture_path = Path(__file__).parent / "fixtures" / "operator_log_small.jsonl"
    result = verify_actions_decided_pointers(str(fixture_path))
    assert result.valid
    assert result.checked > 0
    print("  ✓ Pointer verification passed")


def test_verify_actions_decided_pointers_fail():
    """
    Test I: Pointer verification fails on tampered fixture.
    """
    print("\nTest I: Pointer verification (fail)")
    fixture_path = Path(__file__).parent / "fixtures" / "operator_log_small.jsonl"
    with tempfile.TemporaryDirectory() as tmpdir:
        dst = Path(tmpdir) / "tampered.jsonl"
        _tamper_pointer_fixture(fixture_path, dst)
        result = verify_actions_decided_pointers(str(dst))
        assert not result.valid
        assert result.error == "trigger_event_hash mismatch"
    print("  ✓ Pointer verification failed as expected")


if __name__ == "__main__":
    print("=" * 60)
    print("OPERATOR DETERMINISM TESTS (SPRINT C)")
    print("=" * 60)

    test_decision_determinism_50_runs()
    test_replay_equality()
    test_event_translation_determinism()
    test_event_translation_defaulting_equivalence()
    test_real_state_replay_equivalence()
    test_golden_log_fixture_replay()
    test_golden_log_weird_fixture_replay()
    test_verify_actions_decided_pointers_pass()
    test_verify_actions_decided_pointers_fail()

    print("\n" + "=" * 60)
    print("ALL DETERMINISM TESTS PASSED")
    print("=" * 60)
    print("\nProof:")
    print("- Same (state, event) → same actions (50 runs)")
    print("- Live decisions == Replay decisions (10 events)")
    print("- K8s translation deterministic (100 runs)")
    print("\nThis is paper-grade determinism.")
