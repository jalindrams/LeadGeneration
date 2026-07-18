"""
Micraft Growth Engine - Structured Logging
Provides consistent, structured logging across all modules.
"""

import sys
import structlog
from app.config import settings


def setup_logging():
    """Configure structlog for the application."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if settings.LOG_LEVEL == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.LOG_LEVEL.upper(), structlog.INFO) if hasattr(structlog, settings.LOG_LEVEL.upper()) else 20
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """Get a structured logger instance."""
    log = structlog.get_logger()
    if name:
        log = log.bind(module=name)
    return log
