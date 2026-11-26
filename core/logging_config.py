"""Structured logging setup using structlog.

Usage in any module::

    import logging
    logger = logging.getLogger(__name__)
    logger.info("collected", company="reso", fields_found=11)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Generator

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Set up structured console logging for the application.

    In production (Vercel) the output is consumed by the platform's log
    aggregator; locally it renders pretty for readability.
    """
    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.FilteringBoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


@contextmanager
def timing(name: str, **extra: Any) -> Generator[dict[str, Any], None, None]:
    """Context manager that logs duration of a block."""
    start = time.monotonic()
    ctx: dict[str, Any] = {"op": name, **extra}
    try:
        yield ctx
    finally:
        duration = time.monotonic() - start
        ctx["duration_s"] = round(duration, 3)


def log_exception(logger: logging.Logger, exc: Exception, context: dict[str, Any] | None = None) -> None:
    """Log an exception with structured context instead of bare except."""
    base = {"exception": type(exc).__name__, "message": str(exc)}
    if context:
        base.update(context)
    logger.exception("operation_failed", **base)
