import kopf
import kubernetes
import sys
import os
from .reconcile import ensure_agent_runtime
from .task_controller import TaskController
from .team_controller import TeamController
from .message_controller import MessageController
from .metric_controller import MetricController

# Engine integration imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
from engine.log import FileEventStore
from engine.core import Reducer
from engine.core.clock import DeterministicClock
from engine.replay import replay
from .engine_adapter import EngineAdapter
from .decision_layer import DecisionLayer, actions_to_canonical, action_id
from .executor_layer import ExecutorLayer
from .reducer_handlers import register_handlers, UNIVERSE_AGG_ID
from .leader_election import LeaderElector
from engine.core import Event
from engine.core.canonical import canonical_json_str
import hashlib

# Initialize engine components (global for operator)
event_store_path = os.getenv("EVENT_STORE_PATH", "/var/log/rynxs/operator-events.log")
event_store = FileEventStore(event_store_path)
clock = DeterministicClock(current=0)
adapter = EngineAdapter(clock)
decision_layer = DecisionLayer()
reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
register_handlers(reducer)
writer_id = os.getenv("RYNXS_WRITER_ID")
leader_elector = LeaderElector.from_env()


def _require_leader(logger) -> bool:
    if not leader_elector.is_enabled():
        return True
    if leader_elector.is_leader():
        return True
    logger.info("Standby: not leader, skipping reconcile")
    return False


def _with_writer_id(event: Event) -> Event:
    if not writer_id:
        return event
    meta = dict(event.meta or {})
    if meta.get("writer_id") == writer_id:
        return event
    meta["writer_id"] = writer_id
    return Event(
        type=event.type,
        aggregate_id=event.aggregate_id,
        ts=event.ts,
        payload=event.payload,
        meta=meta,
        seq=event.seq,
    )

kubernetes.config.load_incluster_config()

@kopf.on.startup()
def _startup(settings: kopf.OperatorSettings, **_):
    settings.posting.level = "INFO"

@kopf.on.create('universe.ai', 'v1alpha1', 'agents')
@kopf.on.update('universe.ai', 'v1alpha1', 'agents')
def agent_reconcile(spec, name, namespace, logger, meta, **_):
    if not _require_leader(logger):
        return
    logger.info(f"Reconciling Agent {namespace}/{name} (engine-driven)")

    # Extract labels from metadata
    labels = meta.get("labels", {})

    # Step 1: Translate K8s object → Event (deterministic)
    event = adapter.agent_to_event(name, namespace, spec, labels)
    logger.debug(f"Translated to event: type={event.type}, aggregate_id={event.aggregate_id}")

    # Step 2: Append event to log (hash chain + sequence, CAS retry)
    try:
        append_result = event_store.append_with_retry(_with_writer_id(event))
        event_stored = append_result.event
        logger.info(f"Logged event seq={event_stored.seq}, hash_chain=OK")
    except Exception as e:
        logger.error(f"Failed to append event: {e}")
        raise

    # Capture trigger event hash for decision ledger
    trigger_event_hash = append_result.event_hash or event_store.get_event_hash(event_stored.seq)
    if not trigger_event_hash:
        raise ValueError(f"Missing event_hash for seq={event_stored.seq}")

    # Step 3: Replay to get current state (deterministic)
    try:
        replay_result = replay(event_store, reducer)
        state = replay_result.state
        logger.debug(f"Replayed {replay_result.applied} events, state_version={state.version}")
    except Exception as e:
        logger.error(f"Replay failed: {e}")
        raise

    # Step 4: Decide actions (pure, deterministic)
    try:
        actions = decision_layer.decide(state, event_stored)
        logger.info(f"Decided {len(actions)} actions: {[a.action_type for a in actions]}")
    except Exception as e:
        logger.error(f"Decision layer failed: {e}")
        raise

    # Step 4.5: Log decision ledger (ActionsDecided)
    try:
        actions_canonical = actions_to_canonical(actions)
        actions_json = canonical_json_str(actions_canonical)
        actions_hash = hashlib.sha256(actions_json.encode("utf-8")).hexdigest()
        decision_event = _with_writer_id(Event(
            type="ActionsDecided",
            aggregate_id=event_stored.aggregate_id,
            ts=clock.now(),
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
            meta={"source": "decision_layer"},
        ))
        event_store.append_with_retry(decision_event)
    except Exception as e:
        logger.error(f"Failed to log ActionsDecided: {e}")
        raise

    # Step 5: Execute actions (side effects)
    try:
        executor = ExecutorLayer(event_store, clock, logger)
        feedback_events = executor.apply(actions)
        logger.info(f"Executed actions, logged {len(feedback_events)} feedback events")
    except Exception as e:
        logger.error(f"Executor failed: {e}")
        raise

    logger.info(f"Agent {namespace}/{name} reconciliation complete (engine loop)")

# Legacy fallback (for testing without engine loop)
def agent_reconcile_legacy(spec, name, namespace, logger, **_):
    """Legacy reconcile path (direct K8s API calls)"""
    logger.info(f"Reconciling Agent {namespace}/{name} (legacy mode)")
    ensure_agent_runtime(agent_name=name, namespace=namespace, agent_spec=spec, logger=logger)

@kopf.on.create('universe.ai', 'v1alpha1', 'tasks')
@kopf.on.update('universe.ai', 'v1alpha1', 'tasks')
def task_reconcile(spec, name, namespace, status, logger, **_):
    if not _require_leader(logger):
        return
    logger.info(f"Reconciling Task {namespace}/{name}")
    controller = TaskController(namespace, logger)

    phase = status.get("phase", "Pending")
    if phase in ["Completed", "Failed", "Cancelled"]:
        logger.debug(f"Task {name} already in terminal state: {phase}")
        return

    dependencies = spec.get("dependencies", [])
    if dependencies:
        if not controller.check_dependencies(name, dependencies):
            logger.info(f"Task {name} waiting for dependencies")
            return

    if phase == "Pending":
        controller.assign_task(name, spec)

@kopf.on.create('universe.ai', 'v1alpha1', 'teams')
@kopf.on.update('universe.ai', 'v1alpha1', 'teams')
def team_reconcile(spec, name, namespace, logger, **_):
    if not _require_leader(logger):
        return
    logger.info(f"Reconciling Team {namespace}/{name}")
    controller = TeamController(namespace, logger)
    status = controller.reconcile_team(name, spec)
    return {"status": status}

@kopf.on.create('universe.ai', 'v1alpha1', 'messages')
def message_reconcile(spec, name, namespace, logger, **_):
    if not _require_leader(logger):
        return
    logger.info(f"Processing Message {namespace}/{name}")
    controller = MessageController(namespace, logger)
    status = controller.process_message(name, spec)
    return {"status": status}

@kopf.on.create('universe.ai', 'v1alpha1', 'metrics')
@kopf.on.update('universe.ai', 'v1alpha1', 'metrics')
def metric_reconcile(spec, name, namespace, logger, **_):
    if not _require_leader(logger):
        return
    logger.info(f"Processing Metric {namespace}/{name}")
    controller = MetricController(namespace, logger)
    status = controller.process_metric(name, spec)
    if status:
        return {"status": status}
