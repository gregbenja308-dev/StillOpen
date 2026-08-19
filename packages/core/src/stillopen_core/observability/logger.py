"""Structured logging. URLs, tokens, and extracts are stripped."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

from stillopen_core.config import Environment, get_settings
from stillopen_core.security.redact import safe_log_url

_configured = False

_DROP_KEYS = frozenset(
    {
        "extract",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "cookie",
        "password",
        "client_secret",
        "token_key",
        "api_key",
        "google_api_key",
    }
)


def _redact_event(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict):
        if key.lower() in _DROP_KEYS:
            event_dict[key] = "REDACTED"
        elif key in {"url", "href"} and isinstance(event_dict[key], str):
            event_dict[key] = safe_log_url(event_dict[key])
    return event_dict


def _add_service(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    event_dict.setdefault("service", get_settings().service_name)
    return event_dict


def _configure_once() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_service,
        _redact_event,
    ]
    renderer: Processor
    if settings.env is Environment.CLOUD:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> Any:
    _configure_once()
    return structlog.get_logger(name)


__all__ = ["get_logger"]
