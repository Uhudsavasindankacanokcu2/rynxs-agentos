"""
Structured logging configuration for rynxs operator.

Provides JSON-formatted logs with trace_id support for correlation across
reconciliation loops.

Environment Variables:
    RYNXS_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR) - default: INFO
    RYNXS_LOG_FORMAT: Log format (json, text) - default: json

Usage:
    from operator.universe_operator.logging_config import setup_logging, get_logger

    setup_logging()
    logger = get_logger(__name__, trace_id="agent-12345")
    logger.info("Reconciling agent", extra={"aggregate_id": "agent-12345"})
"""

import logging
import os
import sys
from typing import Optional

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None  # type: ignore


def setup_logging() -> None:
    """
    Configure root logger with structured logging.

    Reads configuration from environment variables:
    - RYNXS_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
    - RYNXS_LOG_FORMAT: json, text (default: json)

    If json format is selected but python-json-logger is not installed,
    falls back to text format with a warning.
    """
    log_level = os.getenv("RYNXS_LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("RYNXS_LOG_FORMAT", "json").lower()

    # Map string log level to logging constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(log_level, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Configure formatter based on format preference
    if log_format == "json" and jsonlogger is not None:
        # JSON formatter with standard fields
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s %(trace_id)s",
            rename_fields={
                "asctime": "timestamp",
                "name": "logger",
                "levelname": "level",
            },
        )
    else:
        if log_format == "json" and jsonlogger is None:
            # Warn about missing dependency
            print(
                "WARNING: python-json-logger not installed, falling back to text format",
                file=sys.stderr,
            )
        # Text formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s [trace_id=%(trace_id)s]",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("kubernetes").setLevel(logging.WARNING)


def get_logger(name: str, trace_id: Optional[str] = None) -> logging.LoggerAdapter:
    """
    Get a logger with optional trace_id for correlation.

    Args:
        name: Logger name (typically __name__)
        trace_id: Trace ID for correlating logs (typically aggregate_id)

    Returns:
        LoggerAdapter with trace_id in extra fields

    Example:
        logger = get_logger(__name__, trace_id="agent-12345")
        logger.info("Processing reconcile")
        # Output (JSON): {"timestamp": "...", "level": "INFO", "message": "Processing reconcile", "trace_id": "agent-12345"}
    """
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, {"trace_id": trace_id or "N/A"})


class TraceIDFilter(logging.Filter):
    """
    Logging filter that adds trace_id to all log records.

    Ensures all logs have a trace_id field, even if not set via LoggerAdapter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = "N/A"  # type: ignore
        return True


# Add filter to root logger (called after setup_logging)
def add_trace_id_filter() -> None:
    """Add TraceIDFilter to root logger (ensures all logs have trace_id field)."""
    root_logger = logging.getLogger()
    root_logger.addFilter(TraceIDFilter())
