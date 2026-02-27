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
import hashlib
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from kubernetes import client
from engine.log import EventStore
from engine.core import Event
from engine.core.clock import DeterministicClock
from engine.core.canonical import canonical_json_bytes, canonicalize
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

    def __init__(self, event_store: EventStore, clock: DeterministicClock, logger, leader_elector=None):
        """
        Initialize executor with event store and K8s clients.

        Args:
            event_store: Event store for logging feedback
            clock: Deterministic clock for event timestamps
            logger: Logger instance
            leader_elector: LeaderElector instance for post-apply verification (optional)
        """
        self.event_store = event_store
        self.clock = clock
        self.logger = logger
        self.leader_elector = leader_elector
        self.writer_id = os.getenv("RYNXS_WRITER_ID")

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

    def _meta_with_writer(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        if not self.writer_id:
            return meta
        merged = dict(meta or {})
        merged.setdefault("writer_id", self.writer_id)
        return merged

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
                result = self._apply_action(action)

                # Post-apply leader check (E3 post-review: fencing mitigation)
                # Verify we're still leader AFTER side-effect to detect late leadership loss
                if self.leader_elector and not self.leader_elector.is_leader():
                    self.logger.warn(
                        f"Leadership lost AFTER applying action {action.action_type}. "
                        "Aborting further actions to prevent split-brain."
                    )
                    # Do NOT log ActionApplied event if we lost leadership
                    # This prevents duplicate events from old leader
                    break

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
                        "result_code": result.get("reason_code"),
                        "resource_ref": result.get("resource_ref"),
                        "operation": result.get("operation"),
                        "noop": result.get("noop"),
                        "status_code": result.get("status_code"),
                        "desired_hash": result.get("desired_hash"),
                        "observed_hash": result.get("observed_hash"),
                    },
                    meta=self._meta_with_writer({"executor": "k8s"}),
                )
                stored_event = self.event_store.append_with_retry(event).event
                feedback_events.append(stored_event)
                self.logger.info(
                    f"Action {action.action_type} applied to {action.target}"
                )

            except Exception as e:
                self.logger.error(f"Failed to apply action {action.action_type}: {e}")

                stable_error = self._stable_error(e)
                desired_hash = self._desired_hash(action)
                resource_ref = self._resource_ref(action)

                # Log failure
                event = Event(
                    type="ActionFailed",
                    aggregate_id=action.target,
                    ts=self.clock.tick().now(),
                    payload={
                        "action_id": action_uid,
                        "action_type": action.action_type,
                        "target": action.target,
                        "resource_ref": resource_ref,
                        "desired_hash": desired_hash,
                        "result_code": stable_error.get("code"),
                        "error": stable_error,
                    },
                    meta=self._meta_with_writer({"executor": "k8s"}),
                )
                stored_event = self.event_store.append_with_retry(event).event
                feedback_events.append(stored_event)

        return feedback_events

    def _apply_action(self, action: Action) -> Dict[str, Any]:
        if action.action_type == "EnsureConfigMap":
            return self._ensure_config_map(action)
        if action.action_type == "EnsurePVC":
            return self._ensure_pvc(action)
        if action.action_type == "EnsureDeployment":
            return self._ensure_deployment(action)
        if action.action_type == "EnsureNetworkPolicy":
            return self._ensure_network_policy(action)
        raise ValueError(f"Unknown action type: {action.action_type}")

    def _resource_ref(self, action: Action) -> str:
        kind = {
            "EnsureConfigMap": "ConfigMap",
            "EnsurePVC": "PersistentVolumeClaim",
            "EnsureDeployment": "Deployment",
            "EnsureNetworkPolicy": "NetworkPolicy",
        }.get(action.action_type, "Unknown")
        name = action.params.get("name")
        namespace = action.params.get("namespace")
        return f"{kind}/{namespace}/{name}"

    def _hash_obj(self, obj: Any) -> str:
        canon = canonicalize(obj if obj is not None else {})
        return hashlib.sha256(canonical_json_bytes(canon)).hexdigest()

    def _desired_hash(self, action: Action) -> str:
        if action.action_type == "EnsureDeployment":
            spec = self._normalize_deployment_spec(action.params.get("spec", {}))
            return self._hash_obj(spec)
        if action.action_type == "EnsureNetworkPolicy":
            spec = self._normalize_network_policy_spec(action.params)
            return self._hash_obj(spec)
        if action.action_type == "EnsureConfigMap":
            return self._hash_obj(action.params.get("data", {}))
        if action.action_type == "EnsurePVC":
            spec = self._normalize_pvc_spec(action.params)
            return self._hash_obj(spec)
        return self._hash_obj(action.params)

    def _normalize_deployment_spec(self, spec: dict) -> dict:
        spec = dict(spec or {})
        spec.pop("image_verify", None)
        spec["env"] = sorted(spec.get("env", []), key=lambda e: e.get("name", ""))
        spec["volume_mounts"] = sorted(
            spec.get("volume_mounts", []),
            key=lambda v: (v.get("name", ""), v.get("mount_path", "")),
        )
        spec["volumes"] = sorted(spec.get("volumes", []), key=lambda v: v.get("name", ""))
        return spec

    def _deployment_spec_from_obj(self, dep) -> dict:
        template = dep.spec.template.spec
        container = template.containers[0] if template.containers else None

        env = []
        if container and container.env:
            for e in container.env:
                env.append({"name": e.name, "value": e.value})

        volume_mounts = []
        if container and container.volume_mounts:
            for vm in container.volume_mounts:
                volume_mounts.append(
                    {
                        "name": vm.name,
                        "mount_path": vm.mount_path,
                        "read_only": vm.read_only or False,
                    }
                )

        volumes = []
        if template.volumes:
            for vol in template.volumes:
                if vol.persistent_volume_claim:
                    volumes.append({"name": vol.name, "pvc": vol.persistent_volume_claim.claim_name})
                elif vol.config_map:
                    volumes.append({"name": vol.name, "configmap": vol.config_map.name})

        spec = {
            "replicas": dep.spec.replicas,
            "image": container.image if container else None,
            "env": env,
            "runtime_class": template.runtime_class_name,
            "volume_mounts": volume_mounts,
            "volumes": volumes,
        }
        return self._normalize_deployment_spec(spec)

    def _normalize_network_policy_spec(self, params: dict) -> dict:
        return {
            "pod_selector": params.get("pod_selector", {}),
            "policy_type": params.get("policy_type"),
        }

    def _network_policy_spec_from_obj(self, np) -> dict:
        policy_types = [t for t in (np.spec.policy_types or [])]
        egress = np.spec.egress or []
        if "Egress" in policy_types:
            if len(egress) == 0:
                policy_type = "deny-egress"
            else:
                policy_type = "allow-egress"
        else:
            policy_type = "unknown"
        return {
            "pod_selector": ((np.spec.pod_selector.match_labels or {}) if np.spec.pod_selector else {}),
            "policy_type": policy_type,
        }

    def _normalize_pvc_spec(self, params: dict) -> dict:
        return {
            "size": params.get("size"),
            "storage_class": params.get("storage_class"),
        }

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

    def _ensure_config_map(self, action: Action) -> Dict[str, Any]:
        """Create or update ConfigMap."""
        if not self.core_api:
            self.logger.warning("K8s API not available, skipping ConfigMap creation")
            return {
                "resource_ref": self._resource_ref(action),
                "operation": "skip",
                "noop": True,
                "status_code": 0,
                "reason_code": "NO_API",
                "desired_hash": self._desired_hash(action),
                "observed_hash": None,
            }

        name = action.params["name"]
        namespace = action.params["namespace"]
        data = action.params["data"]

        cm = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace), data=data
        )
        desired_hash = self._desired_hash(action)
        resource_ref = self._resource_ref(action)

        try:
            self.core_api.create_namespaced_config_map(namespace, cm)
            self.logger.info(f"Created ConfigMap {namespace}/{name}")
            return {
                "resource_ref": resource_ref,
                "operation": "create",
                "noop": False,
                "status_code": 201,
                "reason_code": "CREATED",
                "desired_hash": desired_hash,
                "observed_hash": desired_hash,
            }
        except client.exceptions.ApiException as e:
            if e.status == 409:  # Already exists
                existing = self.core_api.read_namespaced_config_map(name, namespace)
                observed_hash = self._hash_obj(existing.data or {})
                if observed_hash == desired_hash:
                    self.logger.info(f"ConfigMap {namespace}/{name} already matches (noop)")
                    return {
                        "resource_ref": resource_ref,
                        "operation": "noop",
                        "noop": True,
                        "status_code": 304,
                        "reason_code": "ALREADY_MATCHED",
                        "desired_hash": desired_hash,
                        "observed_hash": observed_hash,
                    }
                self.core_api.patch_namespaced_config_map(name, namespace, cm)
                self.logger.info(f"Updated ConfigMap {namespace}/{name}")
                return {
                    "resource_ref": resource_ref,
                    "operation": "patch",
                    "noop": False,
                    "status_code": 200,
                    "reason_code": "PATCHED",
                    "desired_hash": desired_hash,
                    "observed_hash": observed_hash,
                }
            else:
                raise

    def _ensure_pvc(self, action: Action) -> Dict[str, Any]:
        """Create PersistentVolumeClaim."""
        if not self.core_api:
            self.logger.warning("K8s API not available, skipping PVC creation")
            return {
                "resource_ref": self._resource_ref(action),
                "operation": "skip",
                "noop": True,
                "status_code": 0,
                "reason_code": "NO_API",
                "desired_hash": self._desired_hash(action),
                "observed_hash": None,
            }

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
        desired_hash = self._desired_hash(action)
        resource_ref = self._resource_ref(action)

        try:
            self.core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
            self.logger.info(f"Created PVC {namespace}/{name}")
            return {
                "resource_ref": resource_ref,
                "operation": "create",
                "noop": False,
                "status_code": 201,
                "reason_code": "CREATED",
                "desired_hash": desired_hash,
                "observed_hash": desired_hash,
            }
        except client.exceptions.ApiException as e:
            if e.status == 409:  # Already exists (PVC is immutable after creation)
                self.logger.info(f"PVC {namespace}/{name} already exists (immutable)")
                existing = self.core_api.read_namespaced_persistent_volume_claim(name, namespace)
                observed_hash = self._hash_obj(
                    self._normalize_pvc_spec(
                        {
                            "size": existing.spec.resources.requests.get("storage") if existing.spec.resources else None,
                            "storage_class": existing.spec.storage_class_name,
                        }
                    )
                )
                return {
                    "resource_ref": resource_ref,
                    "operation": "noop",
                    "noop": True,
                    "status_code": 304,
                    "reason_code": "IMMUTABLE_EXISTS",
                    "desired_hash": desired_hash,
                    "observed_hash": observed_hash,
                }
            else:
                raise

    def _ensure_deployment(self, action: Action) -> Dict[str, Any]:
        """Create or update Deployment."""
        if not self.apps_api:
            self.logger.warning("K8s API not available, skipping Deployment creation")
            return {
                "resource_ref": self._resource_ref(action),
                "operation": "skip",
                "noop": True,
                "status_code": 0,
                "reason_code": "NO_API",
                "desired_hash": self._desired_hash(action),
                "observed_hash": None,
            }

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
        desired_hash = self._desired_hash(action)
        resource_ref = self._resource_ref(action)

        try:
            self.apps_api.create_namespaced_deployment(namespace, dep)
            self.logger.info(f"Created Deployment {namespace}/{name}")
            return {
                "resource_ref": resource_ref,
                "operation": "create",
                "noop": False,
                "status_code": 201,
                "reason_code": "CREATED",
                "desired_hash": desired_hash,
                "observed_hash": desired_hash,
            }
        except client.exceptions.ApiException as e:
            if e.status == 409:
                existing = self.apps_api.read_namespaced_deployment(name, namespace)
                observed_spec = self._deployment_spec_from_obj(existing)
                observed_hash = self._hash_obj(observed_spec)
                if observed_hash == desired_hash:
                    self.logger.info(f"Deployment {namespace}/{name} already matches (noop)")
                    return {
                        "resource_ref": resource_ref,
                        "operation": "noop",
                        "noop": True,
                        "status_code": 304,
                        "reason_code": "ALREADY_MATCHED",
                        "desired_hash": desired_hash,
                        "observed_hash": observed_hash,
                    }
                self.apps_api.patch_namespaced_deployment(name, namespace, dep)
                self.logger.info(f"Updated Deployment {namespace}/{name}")
                return {
                    "resource_ref": resource_ref,
                    "operation": "patch",
                    "noop": False,
                    "status_code": 200,
                    "reason_code": "PATCHED",
                    "desired_hash": desired_hash,
                    "observed_hash": observed_hash,
                }
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

    def _ensure_network_policy(self, action: Action) -> Dict[str, Any]:
        """Create NetworkPolicy."""
        if not self.net_api:
            self.logger.warning("K8s API not available, skipping NetworkPolicy creation")
            return {
                "resource_ref": self._resource_ref(action),
                "operation": "skip",
                "noop": True,
                "status_code": 0,
                "reason_code": "NO_API",
                "desired_hash": self._desired_hash(action),
                "observed_hash": None,
            }

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
        desired_hash = self._desired_hash(action)
        resource_ref = self._resource_ref(action)

        try:
            self.net_api.create_namespaced_network_policy(namespace, np)
            self.logger.info(f"Created NetworkPolicy {namespace}/{name}")
            return {
                "resource_ref": resource_ref,
                "operation": "create",
                "noop": False,
                "status_code": 201,
                "reason_code": "CREATED",
                "desired_hash": desired_hash,
                "observed_hash": desired_hash,
            }
        except client.exceptions.ApiException as e:
            if e.status == 409:
                existing = self.net_api.read_namespaced_network_policy(name, namespace)
                observed_spec = self._network_policy_spec_from_obj(existing)
                observed_hash = self._hash_obj(observed_spec)
                if observed_hash == desired_hash:
                    self.logger.info(f"NetworkPolicy {namespace}/{name} already matches (noop)")
                    return {
                        "resource_ref": resource_ref,
                        "operation": "noop",
                        "noop": True,
                        "status_code": 304,
                        "reason_code": "ALREADY_MATCHED",
                        "desired_hash": desired_hash,
                        "observed_hash": observed_hash,
                    }
                self.net_api.patch_namespaced_network_policy(name, namespace, np)
                self.logger.info(f"Updated NetworkPolicy {namespace}/{name}")
                return {
                    "resource_ref": resource_ref,
                    "operation": "patch",
                    "noop": False,
                    "status_code": 200,
                    "reason_code": "PATCHED",
                    "desired_hash": desired_hash,
                    "observed_hash": observed_hash,
                }
            else:
                raise
