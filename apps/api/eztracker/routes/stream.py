"""Live updates: MongoDB change streams → Server-Sent Events (replaces Supabase Realtime).

The browser opens `GET /api/stream?token=…` (EventSource can't send headers) and receives topic names
(`work_items`, `sync_runs`, `courses`); it then refetches. No document contents are pushed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .. import db
from ..auth import verify_token
from ..logs import log

router = APIRouter(prefix="/api", tags=["stream"])
TOPICS = ("work_items", "sync_runs", "courses")


async def _events(request: Request, user_id: str) -> AsyncIterator[str]:
    yield "retry: 5000\n\n"
    pipeline: list[dict[str, Any]] = [{"$match": {
        "ns.coll": {"$in": list(TOPICS)},
        "$or": [{"fullDocument.user_id": user_id}, {"operationType": "delete"}]}}]
    queue: asyncio.Queue[str] = asyncio.Queue()

    async def watch() -> None:
        try:
            async with await db.database().watch(pipeline, full_document="updateLookup") as stream:
                async for change in stream:
                    await queue.put(change["ns"]["coll"])
        except Exception as e:  # noqa: BLE001 — the client falls back to polling
            log.warning("change_stream_failed", error=str(e)[:200])
            await queue.put("__error__")

    task = asyncio.create_task(watch())
    try:
        while not await request.is_disconnected():
            try:
                topic = await asyncio.wait_for(queue.get(), timeout=25)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if topic == "__error__":
                yield "event: degraded\ndata: {}\n\n"
                break
            yield f"data: {json.dumps({'topic': topic})}\n\n"
    finally:
        task.cancel()


@router.get("/stream")
async def stream(request: Request, token: str = Query(min_length=20)) -> StreamingResponse:
    user_id = verify_token(token)
    return StreamingResponse(_events(request, user_id), media_type="text/event-stream",
                             headers={"cache-control": "no-cache", "x-accel-buffering": "no"})
