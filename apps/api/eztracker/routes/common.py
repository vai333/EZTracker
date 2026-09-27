from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key(request: Request) -> str:
    return getattr(request.state, "user_id", None) or get_remote_address(request)


limiter = Limiter(key_func=_key, default_limits=["120/minute"])


def uid_or_404(v: str, what: str = "item") -> str:
    try:
        return str(uuid.UUID(v))
    except ValueError as e:
        raise HTTPException(404, f"{what} not found") from e
