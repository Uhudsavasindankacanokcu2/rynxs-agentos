import kopf
import kubernetes
from .reconcile import ensure_agent_runtime
from .task_controller import TaskController
from .team_controller import TeamController
from .message_controller import MessageController
from .metric_controller import MetricController

kubernetes.config.load_incluster_config()

@kopf.on.startup()
def _startup(settings: kopf.OperatorSettings, **_):
    settings.posting.level = "INFO"

@kopf.on.create('universe.ai', 'v1alpha1', 'agents')
@kopf.on.update('universe.ai', 'v1alpha1', 'agents')
def agent_reconcile(spec, name, namespace, logger, **_):
    logger.info(f"Reconciling Agent {namespace}/{name}")
    ensure_agent_runtime(agent_name=name, namespace=namespace, agent_spec=spec, logger=logger)

@kopf.on.create('universe.ai', 'v1alpha1', 'tasks')
@kopf.on.update('universe.ai', 'v1alpha1', 'tasks')
def task_reconcile(spec, name, namespace, status, logger, **_):
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
    logger.info(f"Reconciling Team {namespace}/{name}")
    controller = TeamController(namespace, logger)
    status = controller.reconcile_team(name, spec)
    return {"status": status}

@kopf.on.create('universe.ai', 'v1alpha1', 'messages')
def message_reconcile(spec, name, namespace, logger, **_):
    logger.info(f"Processing Message {namespace}/{name}")
    controller = MessageController(namespace, logger)
    status = controller.process_message(name, spec)
    return {"status": status}

@kopf.on.create('universe.ai', 'v1alpha1', 'metrics')
@kopf.on.update('universe.ai', 'v1alpha1', 'metrics')
def metric_reconcile(spec, name, namespace, logger, **_):
    logger.info(f"Processing Metric {namespace}/{name}")
    controller = MetricController(namespace, logger)
    status = controller.process_metric(name, spec)
    if status:
        return {"status": status}
