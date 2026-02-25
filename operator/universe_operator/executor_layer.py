"""
Executor layer: Apply actions to Kubernetes cluster.

This is where side effects happen:
- K8s API calls
- Create/update/patch resources
- Log feedback events

Side effects are isolated here for replay determinism.
"""

import sys
import os
import json
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from kubernetes import client
from engine.log import EventStore
from engine.core import Event
from engine.core.clock import DeterministicClock
from .decision_layer import Action, action_id


class ExecutorLayer:
    """
    Executes actions on Kubernetes cluster.

    Responsibilities:
    - Apply actions using K8s API
    - Log ActionApplied / ActionFailed feedback events
    - Handle API errors gracefully

    NOT responsible for:
    - Decision logic (that's in decision_layer)
    - Event translation (that's in engine_adapter)
    """

    def __init__(self, event_store: EventStore, clock: DeterministicClock, logger):
        """
        Initialize executor with event store and K8s clients.

        Args:
            event_store: Event store for logging feedback
            clock: Deterministic clock for event timestamps
            logger: Logger instance
        """
        self.event_store = event_store
        self.clock = clock
        self.logger = logger

        # K8s API clients
        try:
            self.core_api = client.CoreV1Api()
            self.apps_api = client.AppsV1Api()
            self.net_api = client.NetworkingV1Api()
        except Exception as e:
            self.logger.warning(f"K8s API client init failed (may be running outside cluster): {e}")
            self.core_api = None
            self.apps_api = None
            self.net_api = None

    def apply(self, actions: List[Action]) -> List[Event]:
        """
        Apply actions to cluster and return feedback events.

        This is where side effects happen.

        Args:
            actions: List of actions to execute

        Returns:
            List of feedback events (ActionApplied / ActionFailed)
        """
        feedback_events = []

        for action in actions:
            action_uid = action_id(action)
            try:
                if action.action_type == "EnsureConfigMap":
                    self._ensure_config_map(action)
                elif action.action_type == "EnsurePVC":
                    self._ensure_pvc(action)
                elif action.action_type == "EnsureDeployment":
                    self._ensure_deployment(action)
                elif action.action_type == "EnsureNetworkPolicy":
                    self._ensure_network_policy(action)
                else:
                    raise ValueError(f"Unknown action type: {action.action_type}")

                # Log success
                event = Event(
                    type="ActionApplied",
                    aggregate_id=action.target,
                    ts=self.clock.tick().now(),
                    payload={
                        "action_id": action_uid,
                        "action_type": action.action_type,
                        "target": action.target,
                        "status": "success",
                        "result_code": "OK",
                    },
                    meta={"executor": "k8s"},
                )
                stored_event = self.event_store.append(event)
                feedback_events.append(stored_event)
                self.logger.info(
                    f"Action {action.action_type} applied to {action.target}"
                )

            except Exception as e:
                self.logger.error(f"Failed to apply action {action.action_type}: {e}")

                stable_error = self._stable_error(e)

                # Log failure
                event = Event(
                    type="ActionFailed",
                    aggregate_id=action.target,
                    ts=self.clock.tick().now(),
                    payload={
                        "action_id": action_uid,
                        "action_type": action.action_type,
                        "target": action.target,
                        "result_code": stable_error.get("code"),
                        "error": stable_error,
                    },
                    meta={"executor": "k8s"},
                )
                stored_event = self.event_store.append(event)
                feedback_events.append(stored_event)

        return feedback_events

    def _stable_error(self, err: Exception) -> dict:
        """
        Return a stable, deterministic error payload for events.

        Avoids embedding raw exception strings or stack traces.
        """
        code = "UNKNOWN"
        base = {"type": err.__class__.__name__, "code": code}

        # Kubernetes ApiException provides stable fields
        if isinstance(err, client.exceptions.ApiException):
            status = getattr(err, "status", None)
            reason = getattr(err, "reason", None)
            base["status"] = status
            base["reason"] = reason

            if status == 404:
                base["code"] = "K8S_NOT_FOUND"
            elif status == 409:
                base["code"] = "K8S_CONFLICT"
            elif status == 403:
                base["code"] = "K8S_FORBIDDEN"
            elif status == 401:
                base["code"] = "K8S_UNAUTHORIZED"
            elif status == 422:
                base["code"] = "K8S_INVALID"
            elif status and status >= 500:
                base["code"] = "K8S_SERVER_ERROR"
            else:
                base["code"] = "K8S_ERROR"
        return base

    def _ensure_config_map(self, action: Action):
        """Create or update ConfigMap."""
        if not self.core_api:
            self.logger.warning("K8s API not available, skipping ConfigMap creation")
            return

        name = action.params["name"]
        namespace = action.params["namespace"]
        data = action.params["data"]

        cm = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace), data=data
        )

        try:
            self.core_api.create_namespaced_config_map(namespace, cm)
            self.logger.info(f"Created ConfigMap {namespace}/{name}")
        except client.exceptions.ApiException as e:
            if e.status == 409:  # Already exists
                self.core_api.patch_namespaced_config_map(name, namespace, cm)
                self.logger.info(f"Updated ConfigMap {namespace}/{name}")
            else:
                raise

    def _ensure_pvc(self, action: Action):
        """Create PersistentVolumeClaim."""
        if not self.core_api:
            self.logger.warning("K8s API not available, skipping PVC creation")
            return

        name = action.params["name"]
        namespace = action.params["namespace"]
        size = action.params["size"]
        storage_class = action.params.get("storage_class")

        pvc_spec = client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(requests={"storage": size}),
        )

        if storage_class:
            pvc_spec.storage_class_name = storage_class

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace), spec=pvc_spec
        )

        try:
            self.core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
            self.logger.info(f"Created PVC {namespace}/{name}")
        except client.exceptions.ApiException as e:
            if e.status == 409:  # Already exists (PVC is immutable after creation)
                self.logger.info(f"PVC {namespace}/{name} already exists (immutable)")
            else:
                raise

    def _ensure_deployment(self, action: Action):
        """Create or update Deployment."""
        if not self.apps_api:
            self.logger.warning("K8s API not available, skipping Deployment creation")
            return

        name = action.params["name"]
        namespace = action.params["namespace"]
        spec = action.params["spec"]

        # Build Deployment from spec
        dep = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                labels={"app": "universe-agent"},
            ),
            spec=client.V1DeploymentSpec(
                replicas=spec["replicas"],
                selector=client.V1LabelSelector(
                    match_labels={"app": "universe-agent"}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "universe-agent"}),
                    spec=self._build_pod_spec(spec),
                ),
            ),
        )

        try:
            self.apps_api.create_namespaced_deployment(namespace, dep)
            self.logger.info(f"Created Deployment {namespace}/{name}")
        except client.exceptions.ApiException as e:
            if e.status == 409:
                self.apps_api.patch_namespaced_deployment(name, namespace, dep)
                self.logger.info(f"Updated Deployment {namespace}/{name}")
            else:
                raise

    def _build_pod_spec(self, spec: dict) -> client.V1PodSpec:
        """Build PodSpec from deployment spec."""
        # Build environment variables
        env = [client.V1EnvVar(name=e["name"], value=e["value"]) for e in spec["env"]]

        # Build volume mounts
        volume_mounts = []
        for vm in spec["volume_mounts"]:
            volume_mounts.append(
                client.V1VolumeMount(
                    name=vm["name"],
                    mount_path=vm["mount_path"],
                    read_only=vm.get("read_only", False),
                )
            )

        # Build volumes
        volumes = []
        for vol in spec["volumes"]:
            if "pvc" in vol:
                volumes.append(
                    client.V1Volume(
                        name=vol["name"],
                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=vol["pvc"]
                        ),
                    )
                )
            elif "configmap" in vol:
                volumes.append(
                    client.V1Volume(
                        name=vol["name"],
                        config_map=client.V1ConfigMapVolumeSource(name=vol["configmap"]),
                    )
                )

        # Build container
        container = client.V1Container(
            name="runtime",
            image=spec["image"],
            env=env,
            volume_mounts=volume_mounts,
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                read_only_root_filesystem=True,
                allow_privilege_escalation=False,
                capabilities=client.V1Capabilities(drop=["ALL"]),
            ),
        )

        # Build PodSpec
        return client.V1PodSpec(
            runtime_class_name=spec.get("runtime_class", "gvisor"),
            containers=[container],
            volumes=volumes,
        )

    def _ensure_network_policy(self, action: Action):
        """Create NetworkPolicy."""
        if not self.net_api:
            self.logger.warning("K8s API not available, skipping NetworkPolicy creation")
            return

        name = action.params["name"]
        namespace = action.params["namespace"]
        pod_selector = action.params["pod_selector"]
        policy_type = action.params["policy_type"]

        # Build NetworkPolicy based on type
        if policy_type == "allow-egress":
            policy_types = ["Egress"]
            egress = [client.V1NetworkPolicyEgressRule(to=[])]  # Allow all egress
        elif policy_type == "deny-egress":
            policy_types = ["Egress"]
            egress = []  # Deny all egress
        else:
            raise ValueError(f"Unknown policy_type: {policy_type}")

        np = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=pod_selector),
                policy_types=policy_types,
                egress=egress,
            ),
        )

        try:
            self.net_api.create_namespaced_network_policy(namespace, np)
            self.logger.info(f"Created NetworkPolicy {namespace}/{name}")
        except client.exceptions.ApiException as e:
            if e.status == 409:
                self.net_api.patch_namespaced_network_policy(name, namespace, np)
                self.logger.info(f"Updated NetworkPolicy {namespace}/{name}")
            else:
                raise
