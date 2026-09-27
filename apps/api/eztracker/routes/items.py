from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import db
from ..auth import UserId
from ..config import get_settings
from ..pipeline import actions
from .common import limiter, uid_or_404

router = APIRouter(prefix="/api/items", tags=["items"])

Kind = Literal["assignment", "workbook", "async_assignment", "form", "announcement_task", "exam", "event", "info"]
Status = Literal["pending", "in_progress", "submitted", "not_applicable"]


class MoveBody(BaseModel):
    course_id: str | None


class StatusBody(BaseModel):
    my_status: Status


class PatchBody(BaseModel):
    my_note: str | None = None
    due_at: datetime | None = None
    due_use_upstream: bool = False
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: Kind | None = None
    is_hidden: bool | None = None


class CreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    course_id: str | None = None
    kind: Kind | None = None
    due_at: datetime | None = None
    instructions_md: str | None = None
    my_note: str | None = None


class UndoBody(BaseModel):
    undo_token: str


class MergeBody(BaseModel):
    keep_id: str
    merge_id: str


async def _act(user_id: str, item_ids: list[str], fn: Any) -> Any:
    state = await db.load_state(user_id, item_ids)
    try:
        result = fn(state)
    except actions.ActionError as e:
        raise HTTPException(e.status, str(e)) from e
    cs = result[1] if isinstance(result, tuple) else result
    await db.apply_changes(user_id, cs)
    return result


# ------------------------------------------------------------------ reads

@router.get("")
async def list_items(user_id: UserId) -> list[dict[str, Any]]:
    return await db.list_items(user_id)


@router.get("/search")
async def search(user_id: UserId, q: str = Query(min_length=1, max_length=100)) -> list[dict[str, Any]]:
    return await db.search_items(user_id, q)


@router.get("/{item_id}/detail")
async def detail(item_id: str, user_id: UserId) -> dict[str, Any]:
    d = await db.item_detail(user_id, uid_or_404(item_id))
    if d is None:
        raise HTTPException(404, "item not found")
    return d


# ------------------------------------------------------------------ writes

@router.patch("/{item_id}/move")
@limiter.limit("60/minute")
async def move(request: Request, item_id: str, body: MoveBody, user_id: UserId) -> dict[str, Any]:
    token, iid = str(uuid.uuid4()), uid_or_404(item_id)
    course = uid_or_404(body.course_id, "course") if body.course_id else None
    await _act(user_id, [iid], lambda s: actions.move_item(s, iid, course, token))
    return {"item": await db.get_item(user_id, iid), "undo_token": token}


@router.patch("/{item_id}/status")
@limiter.limit("60/minute")
async def set_status(request: Request, item_id: str, body: StatusBody, user_id: UserId) -> dict[str, Any]:
    token, iid = str(uuid.uuid4()), uid_or_404(item_id)
    await _act(user_id, [iid], lambda s: actions.set_status(s, iid, body.my_status, token))
    return {"item": await db.get_item(user_id, iid), "undo_token": token}


@router.patch("/{item_id}")
@limiter.limit("60/minute")
async def patch(request: Request, item_id: str, body: PatchBody, user_id: UserId) -> dict[str, Any]:
    token, iid = str(uuid.uuid4()), uid_or_404(item_id)
    data = body.model_dump(exclude_unset=True)
    await _act(user_id, [iid], lambda s: actions.patch_item(s, iid, data, token))
    return {"item": await db.get_item(user_id, iid), "undo_token": token}


@router.post("", status_code=201)
@limiter.limit("60/minute")
async def create(request: Request, body: CreateBody, user_id: UserId) -> dict[str, Any]:
    token = str(uuid.uuid4())
    data = body.model_dump()
    if data.get("course_id"):
        data["course_id"] = uid_or_404(data["course_id"], "course")
    wi, _cs = await _act(user_id, [], lambda s: actions.create_manual(s, data, token))
    return {"item": await db.get_item(user_id, wi.id), "undo_token": token}


@router.post("/undo")
@limiter.limit("60/minute")
async def undo(request: Request, body: UndoBody, user_id: UserId) -> dict[str, Any]:
    token = uid_or_404(body.undo_token, "undo token")
    events = await db.events_for_undo(user_id, token, get_settings().undo_window_seconds)
    ids = sorted({e["work_item_id"] for e in events})
    state = await db.load_state(user_id, ids)
    try:
        cs = actions.undo(state, events, token)
    except actions.ActionError as e:
        raise HTTPException(e.status, str(e)) from e
    await db.apply_changes(user_id, cs)
    await db.burn_undo_token(user_id, token)  # single use
    return {"items": [await db.get_item(user_id, i) for i in ids]}


@router.post("/merge")
@limiter.limit("30/minute")
async def merge(request: Request, body: MergeBody, user_id: UserId) -> dict[str, Any]:
    keep, gone = uid_or_404(body.keep_id), uid_or_404(body.merge_id)
    await _act(user_id, [keep, gone], lambda s: actions.merge_items(s, keep, gone))
    return {"item": await db.get_item(user_id, keep)}
