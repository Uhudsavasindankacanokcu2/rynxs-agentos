"""
Engine adapter: K8s objects → deterministic events.

Normalizes Kubernetes objects to remove nondeterministic fields:
- resourceVersion, uid, managedFields
- timestamps (creationTimestamp, etc.)
- controller-added status fields

Only includes stable, deterministic fields in event payload.
"""

import hashlib
import sys
import os
import copy

# Add engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from engine.core import Event
from engine.core.canonical import canonicalize
from engine.core.clock import DeterministicClock


class EngineAdapter:
    """
    Translates Kubernetes objects to deterministic events.

    Ensures:
    - Same K8s object → same event payload (deterministic)
    - Nondeterministic fields excluded
    - Canonical serialization
    """

    def __init__(self, clock: DeterministicClock):
        """
        Initialize adapter with deterministic clock.

        Args:
            clock: Deterministic clock for event timestamps
        """
        self.clock = clock

    def agent_to_event(
        self, name: str, namespace: str, spec: dict, labels: dict = None, annotations: dict = None
    ) -> Event:
        """
        Translate K8s Agent to deterministic AgentObserved event.

        Excludes nondeterministic fields:
        - resourceVersion, uid, timestamps
        - managedFields, status
        - generation, ownerReferences
        - kubectl annotations (last-applied-configuration, etc.)

        Args:
            name: Agent name
            namespace: Agent namespace
            spec: Agent spec (will be canonicalized)
            labels: Optional labels (will be filtered and sorted)
            annotations: Optional annotations (will be filtered and sorted)

        Returns:
            AgentObserved event with normalized payload
        """
        # Normalize labels (allowlist + sort)
        normalized_labels = {}
        if labels:
            # Allowlist: only stable labels
            stable_keys = ["app", "team", "policy", "role", "network-policy"]
            normalized_labels = {
                k: labels[k] for k in sorted(labels.keys()) if k in stable_keys
            }

        # Normalize annotations (blocklist kubectl-managed ones)
        normalized_annotations = {}
        if annotations:
            # Blocklist: exclude kubectl-managed annotations
            blocked_prefixes = ["kubectl.kubernetes.io/", "deployment.kubernetes.io/"]
            normalized_annotations = {
                k: annotations[k]
                for k in sorted(annotations.keys())
                if not any(k.startswith(prefix) for prefix in blocked_prefixes)
            }

        # Canonical spec (sorted keys, stable structure) with defaults applied
        canonical_spec = self._normalize_agent_spec(spec)

        # Compute spec hash for change detection
        # Use canonical JSON string for deterministic hashing
        from engine.core.canonical import canonical_json_str

        spec_str = canonical_json_str(canonical_spec)
        spec_hash = hashlib.sha256(spec_str.encode("utf-8")).hexdigest()[:16]

        # Build normalized payload
        # Advance logical clock deterministically (immutable clock -> rebind)
        self.clock = self.clock.tick()
        logical_time = self.clock.now()

        payload = {
            "name": name,
            "namespace": namespace,
            "labels": normalized_labels,
            "annotations": normalized_annotations,
            "spec": canonical_spec,
            "spec_hash": spec_hash,
            "observed_logical_time": logical_time,
        }

        # Aggregate ID: namespace/name (stable identifier)
        aggregate_id = f"{namespace}/{name}"

        return Event(
            type="AgentObserved",
            aggregate_id=aggregate_id,
            ts=logical_time,
            payload=payload,
            meta={"source": "kubernetes", "resource": "agents"},
        )

    def _normalize_agent_spec(self, spec: dict) -> dict:
        """
        Normalize agent spec to eliminate K8s defaulting drift.

        Ensures semantically identical specs produce identical payloads.
        """
        def _set_default(d: dict, key: str, value):
            if key not in d or d[key] is None:
                d[key] = value

        # Defensive copy to avoid mutating caller input
        # Convert K8s object to dict if needed
        spec_dict = dict(spec) if spec else {}
        norm = copy.deepcopy(spec_dict)

        # Top-level defaults
        _set_default(norm, "role", "worker")

        # Permissions defaults
        perms = norm.get("permissions") or {}
        _set_default(perms, "canAssignTasks", False)
        _set_default(perms, "canAccessAuditLogs", False)
        _set_default(perms, "canManageTeam", False)
        norm["permissions"] = perms

        # Image defaults
        image = norm.get("image") or {}
        _set_default(image, "tag", "latest")
        _set_default(image, "verify", False)
        norm["image"] = image

        # Workspace defaults
        workspace = norm.get("workspace") or {}
        _set_default(workspace, "size", "1Gi")
        norm["workspace"] = workspace

        return canonicalize(norm)

    def normalize_k8s_list_order(self, items: list, key_func) -> list:
        """
        Sort K8s list by stable key to remove ordering nondeterminism.

        Args:
            items: List of K8s objects
            key_func: Function to extract sort key from item

        Returns:
            Sorted list
        """
        return sorted(items, key=key_func)

    def strip_nondeterministic_fields(self, obj: dict) -> dict:
        """
        Remove nondeterministic fields from K8s object.

        Removes:
        - metadata.resourceVersion
        - metadata.uid
        - metadata.managedFields
        - metadata.creationTimestamp
        - metadata.generation
        - status (all status fields)

        Args:
            obj: K8s object dict

        Returns:
            Cleaned object with only deterministic fields
        """
        cleaned = {}

        # Copy metadata (selectively)
        if "metadata" in obj:
            metadata = obj["metadata"]
            cleaned["metadata"] = {
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace"),
            }

            # Include stable labels
            if "labels" in metadata:
                stable_keys = ["app", "team", "policy", "role", "network-policy"]
                cleaned["metadata"]["labels"] = {
                    k: metadata["labels"][k]
                    for k in sorted(metadata["labels"].keys())
                    if k in stable_keys
                }

            # Include stable annotations (block kubectl-managed)
            if "annotations" in metadata:
                blocked_prefixes = ["kubectl.kubernetes.io/", "deployment.kubernetes.io/"]
                cleaned["metadata"]["annotations"] = {
                    k: metadata["annotations"][k]
                    for k in sorted(metadata["annotations"].keys())
                    if not any(k.startswith(prefix) for prefix in blocked_prefixes)
                }

        # Copy spec (canonical)
        if "spec" in obj:
            cleaned["spec"] = canonicalize(obj["spec"])

        return cleaned
