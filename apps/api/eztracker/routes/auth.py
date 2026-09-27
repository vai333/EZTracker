from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import db
from ..auth import DUMMY_HASH, UserId, issue_token, verify_password
from .common import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
@limiter.limit("10/15minutes")
async def login(request: Request, body: LoginBody) -> dict[str, Any]:
    user = await db.get_user_by_email(body.email)
    ok = verify_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": issue_token(user["_id"], user["email"]), "email": user["email"]}


@router.get("/me")
async def me(user_id: UserId) -> dict[str, Any]:
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(401, "account no longer exists")
    return {"id": user_id, "email": user["email"]}
