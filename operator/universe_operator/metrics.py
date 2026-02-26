"""
Prometheus metrics for rynxs operator.

Exposes operational metrics via HTTP /metrics endpoint for Prometheus scraping.

Environment Variables:
    METRICS_ENABLED: Enable metrics server (true/false) - default: false
    METRICS_PORT: HTTP port for /metrics endpoint - default: 8080
    METRICS_PATH: HTTP path for metrics - default: /metrics (currently unused, always /metrics)

Usage:
    from operator.universe_operator.metrics import start_metrics_server, EVENTS_TOTAL, RECONCILE_DURATION

    start_metrics_server(enabled=True, port=8080)
    
    # Track events
    EVENTS_TOTAL.labels(event_type="AgentObserved").inc()
    
    # Track reconcile duration
    with RECONCILE_DURATION.labels(resource_type="agents").time():
        # ... reconcile logic ...
        pass
"""

import logging
import os
import threading
from contextlib import contextmanager
from typing import Generator

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
except ImportError:
    # Graceful degradation if prometheus_client not installed
    Counter = None  # type: ignore
    Gauge = None  # type: ignore
    Histogram = None  # type: ignore
    start_http_server = None  # type: ignore

logger = logging.getLogger(__name__)

# Metrics registry (module-level, thread-safe)
EVENTS_TOTAL: "Counter" = None  # type: ignore
RECONCILE_DURATION: "Histogram" = None  # type: ignore
LEADER_ELECTION_STATUS: "Gauge" = None  # type: ignore
REPLAY_DURATION: "Histogram" = None  # type: ignore
CHECKPOINT_CREATE_DURATION: "Histogram" = None  # type: ignore
CHECKPOINT_VERIFY_FAILURES: "Counter" = None  # type: ignore

_metrics_initialized = False
_metrics_lock = threading.Lock()


def init_metrics() -> None:
    """
    Initialize Prometheus metrics (call once at startup).

    Creates Counter, Histogram, and Gauge metrics for operator observability.
    Thread-safe via module-level lock.
    """
    global EVENTS_TOTAL, RECONCILE_DURATION, LEADER_ELECTION_STATUS
    global REPLAY_DURATION, CHECKPOINT_CREATE_DURATION, CHECKPOINT_VERIFY_FAILURES
    global _metrics_initialized

    with _metrics_lock:
        if _metrics_initialized:
            return

        if Counter is None:
            logger.warning("prometheus_client not installed, metrics disabled")
            return

        # Event counter (labels: event_type)
        EVENTS_TOTAL = Counter(
            "rynxs_events_total",
            "Total number of events appended to event log",
            labelnames=["event_type"],
        )

        # Reconcile duration histogram (labels: resource_type)
        RECONCILE_DURATION = Histogram(
            "rynxs_reconcile_duration_seconds",
            "Duration of reconcile operations in seconds",
            labelnames=["resource_type"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0),
        )

        # Leader election status gauge (0=follower, 1=leader)
        LEADER_ELECTION_STATUS = Gauge(
            "rynxs_leader_election_status",
            "Leader election status (1=leader, 0=follower)",
        )

        # Replay duration histogram (for CLI/operator internal replay)
        REPLAY_DURATION = Histogram(
            "rynxs_replay_duration_seconds",
            "Duration of event log replay operations in seconds",
            buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
        )

        # Checkpoint creation duration histogram
        CHECKPOINT_CREATE_DURATION = Histogram(
            "rynxs_checkpoint_create_duration_seconds",
            "Duration of checkpoint creation operations in seconds",
            buckets=(0.1, 0.5, 1.0, 5.0, 10.0),
        )

        # Checkpoint verification failure counter
        CHECKPOINT_VERIFY_FAILURES = Counter(
            "rynxs_checkpoint_verify_failures_total",
            "Total number of checkpoint verification failures",
        )

        _metrics_initialized = True
        logger.info("Prometheus metrics initialized")


def start_metrics_server(enabled: bool, port: int) -> None:
    """
    Start Prometheus metrics HTTP server in background thread.

    Args:
        enabled: Whether to start metrics server (from METRICS_ENABLED env var)
        port: HTTP port for /metrics endpoint (from METRICS_PORT env var)

    Side Effects:
        - Starts HTTP server in daemon thread (does not block)
        - Server listens on 0.0.0.0:<port>/metrics
        - Initializes metrics registry if not already initialized

    Example:
        start_metrics_server(enabled=True, port=8080)
        # curl http://localhost:8080/metrics
    """
    if not enabled:
        logger.info("Metrics server disabled (METRICS_ENABLED=false)")
        return

    if start_http_server is None:
        logger.error("prometheus_client not installed, cannot start metrics server")
        return

    # Initialize metrics registry
    init_metrics()

    # Start HTTP server in background thread
    try:
        # start_http_server is non-blocking (starts daemon thread)
        start_http_server(port, addr="0.0.0.0")
        logger.info(f"Metrics server started on http://0.0.0.0:{port}/metrics")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")


@contextmanager
def track_reconcile_duration(resource_type: str) -> Generator[None, None, None]:
    """
    Context manager for tracking reconcile duration.

    Args:
        resource_type: Type of resource being reconciled (e.g., "agents", "sessions")

    Usage:
        with track_reconcile_duration("agents"):
            # ... reconcile logic ...
            pass
    """
    if RECONCILE_DURATION is None:
        yield
        return

    with RECONCILE_DURATION.labels(resource_type=resource_type).time():
        yield


def track_event(event_type: str) -> None:
    """
    Track event appended to event log.

    Args:
        event_type: Type of event (e.g., "AgentObserved", "ActionsDecided")

    Usage:
        track_event("AgentObserved")
    """
    if EVENTS_TOTAL is not None:
        EVENTS_TOTAL.labels(event_type=event_type).inc()


def set_leader_status(is_leader: bool) -> None:
    """
    Set leader election status metric.

    Args:
        is_leader: True if this instance is the leader, False otherwise

    Usage:
        set_leader_status(True)   # This instance became leader
        set_leader_status(False)  # This instance lost leadership
    """
    if LEADER_ELECTION_STATUS is not None:
        LEADER_ELECTION_STATUS.set(1 if is_leader else 0)
