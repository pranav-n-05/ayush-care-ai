"""Structured logging with redaction. Never log clinical payloads, tokens or identifiers."""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

REDACT_KEYS = {
    "password",
    "token",
    "session",
    "cookie",
    "authorization",
    "csrf",
    "answer",
    "value",
    "text",
    "prompt",
    "response",
    "phone",
    "email",
    "name",
    "address",
}


def _redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key == "event":
            continue
        if any(marker in key.lower() for marker in REDACT_KEYS):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )


def get_logger(name: str = "ayushcare") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
