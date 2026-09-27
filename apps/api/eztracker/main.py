from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import db, scheduler
from .config import APP_NAME, get_settings
from .logs import configure_logging, log
from .routes import auth, calendar, courses, credentials, items, stream, sync
from .routes.common import limiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level)
    if s.mongodb_uri:
        await db.ensure_indexes()
        if s.scheduler_enabled:
            await scheduler.start()
    yield
    scheduler.shutdown()
    await db.close()


app = FastAPI(title=f"{APP_NAME} API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_origin], allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["authorization", "content-type"])


@app.middleware("http")
async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path, method=request.method)
    try:
        resp = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    resp.headers["x-request-id"] = rid
    return resp


def problem(status: int, title: str, detail: Any = None, request: Request | None = None) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    if request is not None:
        body["instance"] = request.url.path
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


@app.exception_handler(HTTPException)
async def http_problem(request: Request, exc: HTTPException) -> JSONResponse:
    return problem(exc.status_code, {400: "Bad request", 401: "Unauthorized", 404: "Not found", 409: "Conflict",
                                     410: "Gone", 429: "Too many requests"}.get(exc.status_code, "Error"),
                   exc.detail, request)


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
    # never echo input values back (they may include a password)
    return problem(422, "Validation failed", [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()], request)


@app.exception_handler(RateLimitExceeded)
async def rate_problem(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return problem(429, "Too many requests", str(exc.detail), request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error")
    return problem(500, "Internal error", None, request)


for r in (auth.router, items.router, sync.router, credentials.router, courses.router, calendar.router,
          stream.router):
    app.include_router(r)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    db_ok = False
    if get_settings().mongodb_uri:
        try:
            db_ok = (await db.database().command("ping")).get("ok") == 1
        except Exception:  # noqa: BLE001
            db_ok = False
    return {"ok": True, "app": APP_NAME, "db": db_ok, "scheduler": scheduler.scheduler.running,
            "next_run_at": scheduler.next_run_time()}
