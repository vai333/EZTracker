"""Connect / disconnect Nexus. Request bodies here are never logged."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import crypto, db
from ..auth import UserId
from ..scraper.session import NexusAuthError, open_session
from ..sync import run_sync
from .common import limiter

router = APIRouter(prefix="/api/credentials", tags=["credentials"])
_tasks: set[asyncio.Task[Any]] = set()


class CredentialsBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.get("")
async def status(user_id: UserId) -> dict[str, Any]:
    return await db.connection_status(user_id)


@router.post("")
@limiter.limit("5/hour")
async def connect(request: Request, body: CredentialsBody, user_id: UserId) -> dict[str, Any]:
    captured: dict[str, str] = {}

    async def keep_state(state_json: str) -> None:
        captured["state"] = state_json

    try:
        async with open_session(body.email, lambda: body.password, None, keep_state) as sess:
            captured.setdefault("state", await sess.storage_state_json())
    except NexusAuthError as e:
        raise HTTPException(400, str(e)) from e
    await db.save_credentials(user_id, body.email, crypto.encrypt(body.password), crypto.encrypt(captured["state"]))
    t = asyncio.create_task(run_sync(user_id, "manual"))  # first sync; progress arrives via the live stream
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return await db.connection_status(user_id)


@router.delete("")
async def disconnect(user_id: UserId) -> dict[str, Any]:
    await db.delete_credentials(user_id)
    return {"connected": False}
