from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .. import db, scheduler
from ..auth import UserId
from ..config import get_settings
from ..sync import SyncBusy, run_sync
from .common import limiter

router = APIRouter(prefix="/api/sync", tags=["sync"])
_tasks: set[asyncio.Task[Any]] = set()


@router.post("", status_code=202)
@limiter.limit("6/hour")
async def sync_now(request: Request, user_id: UserId) -> dict[str, Any]:
    s = get_settings()
    last = await db.latest_run(user_id)
    if last and last["started_at"] > datetime.now(UTC) - timedelta(minutes=s.manual_sync_cooldown_minutes):
        retry = last["started_at"] + timedelta(minutes=s.manual_sync_cooldown_minutes)
        raise HTTPException(429, f"last sync started less than {s.manual_sync_cooldown_minutes} min ago; "
                                 f"try again after {retry.isoformat()}")
    if await db.get_credentials(user_id) is None:
        raise HTTPException(400, "Nexus is not connected")
    run_id = await db.create_run(user_id, "manual")

    async def go() -> None:
        try:
            await run_sync(user_id, "manual", run_id=run_id)
        except SyncBusy:
            pass

    t = asyncio.create_task(go())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"run_id": run_id}


@router.get("/status")
async def sync_status(user_id: UserId) -> dict[str, Any]:
    s = get_settings()
    last_ok = await db.last_success_at(user_id)
    stale = last_ok is None or last_ok < datetime.now(UTC) - timedelta(hours=s.stale_after_hours)
    return {"latest": await db.latest_run(user_id), "last_success_at": last_ok,
            "next_run_at": scheduler.next_run_time(), "stale": stale, "interval_hours": s.sync_interval_hours}


@router.get("/runs")
async def runs(user_id: UserId) -> list[dict[str, Any]]:
    return await db.recent_runs(user_id, 20)
