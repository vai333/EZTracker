from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import db
from ..auth import UserId
from ..pipeline.text import normalize
from .common import limiter, uid_or_404

router = APIRouter(prefix="/api/courses", tags=["courses"])


class CoursePatch(BaseModel):
    short_name: str | None = Field(default=None, max_length=40)
    color_index: int | None = Field(default=None, ge=0, le=7)
    is_archived: bool | None = None


class AliasBody(BaseModel):
    alias: str = Field(min_length=2, max_length=60)


async def _own(user_id: str, course_id: str) -> str:
    cid = uid_or_404(course_id, "course")
    if not await db.course_exists(user_id, cid):
        raise HTTPException(404, "course not found")
    return cid


@router.get("")
async def list_courses(user_id: UserId) -> list[dict[str, Any]]:
    return await db.list_courses(user_id)


@router.patch("/{course_id}")
@limiter.limit("60/minute")
async def patch_course(request: Request, course_id: str, body: CoursePatch, user_id: UserId) -> dict[str, Any]:
    cid = await _own(user_id, course_id)
    doc = await db.patch_course(user_id, cid, body.model_dump(exclude_unset=True))
    if doc is None:
        raise HTTPException(404, "course not found")
    return doc


@router.get("/{course_id}/aliases")
async def list_aliases(course_id: str, user_id: UserId) -> list[dict[str, Any]]:
    return await db.list_aliases(user_id, await _own(user_id, course_id))


@router.post("/{course_id}/aliases", status_code=201)
@limiter.limit("60/minute")
async def add_alias(request: Request, course_id: str, body: AliasBody, user_id: UserId) -> dict[str, Any]:
    alias = normalize(body.alias)
    if len(alias) < 2:
        raise HTTPException(422, "alias too short")
    return await db.add_alias(user_id, await _own(user_id, course_id), alias)


@router.delete("/{course_id}/aliases/{alias_id}", status_code=204)
async def delete_alias(course_id: str, alias_id: str, user_id: UserId) -> None:
    await db.delete_alias(user_id, await _own(user_id, course_id), alias_id)
