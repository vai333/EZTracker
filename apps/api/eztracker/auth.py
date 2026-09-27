"""Owner sign-in: email + password (scrypt), API-issued HS256 session tokens.

EZTracker is single-owner: accounts are created only from the command line (`make create-user`), never over
the web. user_id always comes from the verified token, never from a request body.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request

from .config import get_settings

_N, _R, _P, _DKLEN = 2**15, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=_N, r=_R, p=_P, dklen=_DKLEN,
                            maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:  # noqa: BLE001 — malformed hash means "no"
        return False


# a real hash of a random password, so failed logins for unknown emails take the same time
DUMMY_HASH = hash_password(secrets.token_hex(16))


def _secret() -> str:
    s = get_settings().auth_jwt_secret
    if len(s) < 32:
        raise HTTPException(500, "server is missing AUTH_JWT_SECRET (run `make keygen-jwt`)")
    return s


def issue_token(user_id: str, email: str) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user_id, "email": email, "aud": "eztracker", "iat": int(now.timestamp()),
              "exp": int((now + timedelta(days=get_settings().session_days)).timestamp())}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def verify_token(token: str) -> str:
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"], audience="eztracker")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(401, "invalid or expired session") from e
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(401, "token has no subject")
    return str(sub)


def current_user(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    uid = verify_token(auth.split(" ", 1)[1].strip())
    request.state.user_id = uid
    return uid


UserId = Annotated[str, Depends(current_user)]
