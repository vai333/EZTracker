"""structlog setup with a processor that scrubs secrets before anything is written."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

_SECRET_KEYS = re.compile(r"(password|passwd|token|cookie|authorization|secret|storage_state|jwt)", re.I)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")


def _scrub_value(v: Any) -> Any:
    if isinstance(v, str):
        return _JWT.sub("[redacted-jwt]", _BEARER.sub(r"\1[redacted]", v))
    if isinstance(v, dict):
        return {k: ("[redacted]" if _SECRET_KEYS.search(str(k)) else _scrub_value(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub_value(x) for x in v]
    return v


def scrub_secrets(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> dict[str, Any]:
    return {k: ("[redacted]" if _SECRET_KEYS.search(k) else _scrub_value(v)) for k, v in event_dict.items()}


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            scrub_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )


log = structlog.get_logger()
