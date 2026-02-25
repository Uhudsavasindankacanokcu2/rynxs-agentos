"""
Decision layer: Pure state transition logic.

NO side effects. NO K8s API calls. NO I/O.
Pure functions only: (state, event) -> actions

This is the deterministic heart of the operator.
"""

import sys
import os
from dataclasses import dataclass
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from engine.core import State, Event
from engine.core.canonical import canonical_json_str, canonicalize


@dataclass
class Action:
    """Base action class for executor."""

    action_type: str
    target: str  # namespace/name
    params: Dict[str, Any]


@dataclass
class EnsureConfigMapAction(Action):
    """Action: Ensure ConfigMap exists with data."""

    def __init__(self, name: str, namespace: str, data: dict):
        super().__init__(
            action_type="EnsureConfigMap",
            target=f"{namespace}/{name}",
            params={"name": name, "namespace": namespace, "data": data},
        )


@dataclass
class EnsurePVCAction(Action):
    """Action: Ensure PersistentVolumeClaim exists."""

    def __init__(self, name: str, namespace: str, size: str, storage_class: str = None):
        params = {"name": name, "namespace": namespace, "size": size}
        if storage_class:
            params["storage_class"] = storage_class

        super().__init__(
            action_type="EnsurePVC", target=f"{namespace}/{name}", params=params
        )


@dataclass
class EnsureDeploymentAction(Action):
    """Action: Ensure Deployment exists with spec."""

    def __init__(self, name: str, namespace: str, spec: dict):
        super().__init__(
            action_type="EnsureDeployment",
            target=f"{namespace}/{name}",
            params={"name": name, "namespace": namespace, "spec": spec},
        )


@dataclass
class EnsureNetworkPolicyAction(Action):
    """Action: Ensure NetworkPolicy exists."""

    def __init__(self, name: str, namespace: str, pod_selector: dict, policy_type: str):
        super().__init__(
            action_type="EnsureNetworkPolicy",
            target=f"{namespace}/{name}",
            params={
                "name": name,
                "namespace": namespace,
                "pod_selector": pod_selector,
                "policy_type": policy_type,
            },
        )


class DecisionLayer:
    """
    Pure decision logic for operator.

    All decisions are deterministic:
    - Same (state, event) -> same actions (always)
    - No side effects
    - No I/O
    - No randomness
    """

    def decide(self, state: State, event: Event) -> List[Action]:
        """
        Decide actions based on state and event.

        This is the core decision function. MUST be pure.

        Args:
            state: Current state (from replay)
            event: Input event

        Returns:
            List of actions to execute
        """
        if event.type == "AgentObserved":
            actions = self._decide_agent_observed(state, event)
            return self._stable_actions(actions)
        elif event.type == "ActionApplied":
            # No further actions needed for feedback events
            return []
        elif event.type == "ActionFailed":
            # Could add retry logic here
            return []
        else:
            # Unknown event type - no action
            return []

    def _stable_actions(self, actions: List[Action]) -> List[Action]:
        """
        Ensure deterministic ordering of actions.
        """
        def _key(a: Action):
            try:
                params_key = canonical_json_str(a.params)
            except Exception:
                params_key = str(a.params)
            return (a.action_type, a.target, params_key)

        return sorted(actions, key=_key)

    def _decide_agent_observed(self, state: State, event: Event) -> List[Action]:
        """
        Decide actions when Agent is observed.

        Creates:
        1. ConfigMap with agent spec
        2. PVC for workspace
        3. Deployment for runtime
        4. NetworkPolicy (optional, based on role)

        Args:
            state: Current state
            event: AgentObserved event

        Returns:
            List of actions
        """
        actions = []

        name = event.payload["name"]
        namespace = event.payload["namespace"]
        spec = event.payload["spec"]

        # Decision 1: Ensure ConfigMap with agent spec
        # Store canonical spec for agent runtime to read
        actions.append(
            EnsureConfigMapAction(
                name=f"{name}-spec",
                namespace=namespace,
                data={"agent.json": canonical_json_str(spec)},
            )
        )

        # Decision 2: Ensure PVC for workspace
        workspace = spec.get("workspace", {})
        size = workspace.get("size", "1Gi")
        storage_class = workspace.get("storageClassName")

        actions.append(
            EnsurePVCAction(
                name=f"{name}-workspace",
                namespace=namespace,
                size=size,
                storage_class=storage_class,
            )
        )

        # Decision 3: Ensure Deployment for agent runtime
        image_spec = spec.get("image", {})
        image_repo = image_spec.get("repository", "rynxs/universal-agent-runtime")
        image_tag = image_spec.get("tag", "latest")
        image = f"{image_repo}:{image_tag}"

        # Build deployment spec (canonical, deterministic)
        deployment_spec = canonicalize({
            "replicas": 1,
            "image": image,
            "image_verify": image_spec.get("verify", False),
            "env": [
                {"name": "AGENT_NAME", "value": name},
                {"name": "AGENT_NAMESPACE", "value": namespace},
            ],
            "runtime_class": "gvisor",
            "volumes": [
                {"name": "workspace", "pvc": f"{name}-workspace"},
                {"name": "agent-spec", "configmap": f"{name}-spec"},
            ],
            "volume_mounts": [
                {"name": "workspace", "mount_path": "/workspace"},
                {"name": "agent-spec", "mount_path": "/config", "read_only": True},
            ],
        })

        actions.append(
            EnsureDeploymentAction(
                name=f"{name}-runtime", namespace=namespace, spec=deployment_spec
            )
        )

        # Decision 4: NetworkPolicy based on role
        role = spec.get("role", "worker")
        permissions = spec.get("permissions", {})

        # Directors/managers get egress permissions
        if role in ["director", "manager"] or permissions.get("canAssignTasks"):
            actions.append(
                EnsureNetworkPolicyAction(
                    name=f"{name}-allow-egress",
                    namespace=namespace,
                    pod_selector={"app": "universe-agent", "agent": name},
                    policy_type="allow-egress",
                )
            )
        else:
            # Workers get restricted egress
            actions.append(
                EnsureNetworkPolicyAction(
                    name=f"{name}-deny-egress",
                    namespace=namespace,
                    pod_selector={"app": "universe-agent", "agent": name},
                    policy_type="deny-egress",
                )
            )

        return actions
