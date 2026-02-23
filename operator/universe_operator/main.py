import kopf
import kubernetes
from .reconcile import ensure_agent_runtime

kubernetes.config.load_incluster_config()

@kopf.on.startup()
def _startup(settings: kopf.OperatorSettings, **_):
    settings.posting.level = "INFO"

@kopf.on.create('universe.ai', 'v1alpha1', 'agents')
@kopf.on.update('universe.ai', 'v1alpha1', 'agents')
def agent_reconcile(spec, name, namespace, logger, **_):
    logger.info(f"Reconciling Agent {namespace}/{name}")
    ensure_agent_runtime(agent_name=name, namespace=namespace, agent_spec=spec, logger=logger)
