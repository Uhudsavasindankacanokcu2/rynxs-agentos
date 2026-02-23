from kubernetes import client

class BindingController:
    """
    Implements the Binding primitive: attachment of consciousness -> pod.
    """
    def __init__(self, logger):
        self.logger = logger

    def resolve_consciousness(self, agent_spec: dict) -> dict:
        """
        Resolves consciousness metadata from the agent spec.
        Currently handles 'consciousness' field if present.
        """
        consciousness = agent_spec.get("consciousness", {})
        if not consciousness:
            self.logger.info("No consciousness defined in spec, using defaults.")
            return {"id": "default", "name": "Default Consciousness"}
        return consciousness

    def apply_binding_to_spec(self, pod_spec: client.V1PodSpec, consciousness: dict):
        """
        Injects consciousness ID and name into the pod environment.
        This represents the 'attachment'.
        """
        container = pod_spec.containers[0]
        if not container.env:
            container.env = []
        
        container.env.append(client.V1EnvVar(name="CONSCIOUSNESS_ID", value=consciousness.get("id", "default")))
        container.env.append(client.V1EnvVar(name="CONSCIOUSNESS_NAME", value=consciousness.get("name", "Default")))
        
        self.logger.info(f"Bound consciousness {consciousness.get('id')} to pod spec.")
