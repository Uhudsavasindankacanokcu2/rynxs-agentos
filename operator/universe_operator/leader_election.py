"""
Leader election using Kubernetes Lease objects.

Default mode: enabled only when RYNXS_LEADER_ELECTION_ENABLED=1.
"""

from __future__ import annotations

import os
import time
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client
from kubernetes.client.rest import ApiException


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_namespace() -> str:
    env_ns = (
        os.getenv("RYNXS_OPERATOR_NAMESPACE")
        or os.getenv("POD_NAMESPACE")
        or os.getenv("WATCH_NAMESPACE")
    )
    if env_ns:
        return env_ns
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
            return f.read().strip()
    except OSError:
        return "default"


def _read_identity() -> str:
    return (
        os.getenv("RYNXS_LEADER_ID")
        or os.getenv("RYNXS_WRITER_ID")
        or os.getenv("POD_NAME")
        or os.getenv("HOSTNAME")
        or "rynxs-operator"
    )


@dataclass
class LeaderElectionConfig:
    enabled: bool
    lease_name: str
    lease_duration_seconds: int
    renew_deadline_seconds: int
    retry_period_seconds: int

    @staticmethod
    def from_env() -> "LeaderElectionConfig":
        enabled = os.getenv("RYNXS_LEADER_ELECTION_ENABLED", "0") == "1"
        lease_name = os.getenv("RYNXS_LEASE_NAME", "rynxs-operator-leader")
        lease_duration_seconds = int(os.getenv("RYNXS_LEASE_DURATION_SECONDS", "30"))
        renew_deadline_seconds = int(os.getenv("RYNXS_RENEW_DEADLINE_SECONDS", "20"))
        retry_period_seconds = int(os.getenv("RYNXS_RETRY_PERIOD_SECONDS", "5"))
        return LeaderElectionConfig(
            enabled=enabled,
            lease_name=lease_name,
            lease_duration_seconds=lease_duration_seconds,
            renew_deadline_seconds=renew_deadline_seconds,
            retry_period_seconds=retry_period_seconds,
        )


class LeaderElector:
    def __init__(
        self,
        namespace: str,
        identity: str,
        config: LeaderElectionConfig,
    ) -> None:
        self.namespace = namespace
        self.identity = identity
        self.config = config
        self._leader = False
        self._last_check = 0.0
        self._api = client.CoordinationV1Api()

    @classmethod
    def from_env(cls) -> "LeaderElector":
        return cls(
            namespace=_read_namespace(),
            identity=_read_identity(),
            config=LeaderElectionConfig.from_env(),
        )

    def is_enabled(self) -> bool:
        return self.config.enabled

    def is_leader(self) -> bool:
        if not self.config.enabled:
            return True
        now = time.time()
        if now - self._last_check < self.config.retry_period_seconds:
            return self._leader
        return self.ensure_leader()

    def ensure_leader(self) -> bool:
        if not self.config.enabled:
            self._leader = True
            return True

        now = time.time()
        self._last_check = now

        try:
            lease = self._api.read_namespaced_lease(self.config.lease_name, self.namespace)
        except ApiException as ex:
            if ex.status == 404:
                return self._create_lease()
            self._leader = False
            return False

        spec = lease.spec
        if spec is None:
            self._leader = False
            return False

        if spec.holder_identity == self.identity:
            return self._renew_lease(lease)

        if self._is_expired(spec):
            return self._takeover_lease(lease)

        self._leader = False
        return False

    def _create_lease(self) -> bool:
        now = _now()
        spec = client.V1LeaseSpec(
            holder_identity=self.identity,
            lease_duration_seconds=self.config.lease_duration_seconds,
            acquire_time=now,
            renew_time=now,
        )
        lease = client.V1Lease(
            metadata=client.V1ObjectMeta(
                name=self.config.lease_name,
                namespace=self.namespace,
            ),
            spec=spec,
        )
        try:
            self._api.create_namespaced_lease(self.namespace, lease)
            self._leader = True
            return True
        except ApiException:
            self._leader = False
            return False

    def _renew_lease(self, lease: client.V1Lease) -> bool:
        """Renew lease with 409 retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            lease.spec.renew_time = _now()
            lease.spec.lease_duration_seconds = self.config.lease_duration_seconds
            try:
                self._api.replace_namespaced_lease(
                    name=self.config.lease_name,
                    namespace=self.namespace,
                    body=lease,
                )
                self._leader = True
                return True
            except ApiException as ex:
                if ex.status == 409 and attempt < max_retries - 1:
                    # 409 Conflict: resourceVersion mismatch, retry with fresh lease
                    backoff = (2 ** attempt) * 0.1 + random.uniform(0, 0.2)  # Exponential + jitter (0-200ms)
                    time.sleep(backoff)
                    try:
                        lease = self._api.read_namespaced_lease(self.config.lease_name, self.namespace)
                        # Verify we still hold the lease
                        if lease.spec and lease.spec.holder_identity != self.identity:
                            self._leader = False
                            self._track_failure("lost_lease_during_renew")
                            return False
                        # Continue retry loop with fresh lease
                    except ApiException:
                        self._leader = False
                        self._track_failure("api_error_during_retry")
                        return False
                else:
                    # Non-409 error or max retries exceeded
                    self._leader = False
                    if ex.status == 409:
                        self._track_failure("conflict_retries_exhausted")
                    else:
                        self._track_failure("api_error")
                    return False
        self._leader = False
        self._track_failure("conflict_retries_exhausted")
        return False

    def _takeover_lease(self, lease: client.V1Lease) -> bool:
        """Takeover expired lease with 409 retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            now = _now()
            lease.spec.holder_identity = self.identity
            lease.spec.acquire_time = now
            lease.spec.renew_time = now
            lease.spec.lease_duration_seconds = self.config.lease_duration_seconds
            try:
                self._api.replace_namespaced_lease(
                    name=self.config.lease_name,
                    namespace=self.namespace,
                    body=lease,
                )
                self._leader = True
                return True
            except ApiException as ex:
                if ex.status == 409 and attempt < max_retries - 1:
                    # 409 Conflict: another pod may have taken leadership, retry with fresh lease
                    backoff = (2 ** attempt) * 0.1 + random.uniform(0, 0.2)  # Exponential + jitter (0-200ms)
                    time.sleep(backoff)
                    try:
                        lease = self._api.read_namespaced_lease(self.config.lease_name, self.namespace)
                        # Verify lease is still expired before retrying takeover
                        if lease.spec and not self._is_expired(lease.spec):
                            # Someone else renewed it, we lost the race
                            self._leader = False
                            self._track_failure("lost_takeover_race")
                            return False
                        # Continue retry loop with fresh lease
                    except ApiException:
                        self._leader = False
                        self._track_failure("api_error_during_retry")
                        return False
                else:
                    # Non-409 error or max retries exceeded
                    self._leader = False
                    if ex.status == 409:
                        self._track_failure("conflict_retries_exhausted")
                    else:
                        self._track_failure("api_error")
                    return False
        self._leader = False
        self._track_failure("conflict_retries_exhausted")
        return False

    def _is_expired(self, spec: client.V1LeaseSpec) -> bool:
        base = spec.renew_time or spec.acquire_time
        if base is None:
            return True
        age = (_now() - base).total_seconds()
        duration = spec.lease_duration_seconds or self.config.lease_duration_seconds
        return age > duration

    def _track_failure(self, reason: str) -> None:
        """Track leader election failure metric (E4.4)."""
        try:
            from .metrics import track_leader_election_failure
            track_leader_election_failure(reason)
        except Exception:
            # Metrics may not be initialized, ignore
            pass
