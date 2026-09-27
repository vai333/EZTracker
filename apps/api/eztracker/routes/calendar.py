""".ics feed of pending dated items (§13), per-user secret token; plus data export."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .. import db
from ..auth import UserId
from ..config import APP_NAME

router = APIRouter(prefix="/api", tags=["calendar"])


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, b = [], line.encode()
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:  # never split a UTF-8 sequence
            cut -= 1
        out.append(b[:cut].decode())
        b = b" " + b[cut:]
    out.append(b.decode())
    return "\r\n".join(out)


def build_ics(items: list[dict[str, Any]]) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{APP_NAME}//EN", f"X-WR-CALNAME:{APP_NAME} deadlines",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for it in items:
        due = it["due_at"].astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        title = f"{it['short_name'] + ' · ' if it.get('short_name') else ''}{it['title']}"
        link = next((lk["url"] for lk in (it.get("links") or []) if lk.get("label") == "Open in Nexus"), "")
        lines += ["BEGIN:VEVENT", f"UID:{it['id']}@eztracker", f"DTSTAMP:{stamp}", f"DTSTART:{due}", f"DTEND:{due}",
                  _fold(f"SUMMARY:{_esc(title)}"), _fold(f"DESCRIPTION:{_esc(link)}"),
                  "BEGIN:VALARM", "TRIGGER:-PT24H", "ACTION:DISPLAY", "DESCRIPTION:Due in 24 hours", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@router.get("/calendar.ics")
async def calendar(token: str = Query(min_length=16, max_length=128)) -> Response:
    uid = await db.user_for_calendar_token(token)
    if uid is None:
        raise HTTPException(404, "unknown calendar token")
    return Response(build_ics(await db.calendar_items(uid)), media_type="text/calendar; charset=utf-8")


@router.get("/settings/calendar")
async def calendar_settings(user_id: UserId) -> dict[str, str]:
    return {"path": f"/api/calendar.ics?token={await db.calendar_token(user_id)}"}


@router.post("/settings/calendar/rotate")
async def rotate_calendar(user_id: UserId) -> dict[str, str]:
    return {"path": f"/api/calendar.ics?token={await db.calendar_token(user_id, rotate=True)}"}


EXPORT_COLS = ["id", "title", "course", "kind", "origin", "due_at", "my_status", "nexus_status", "classification",
               "confidence", "my_note", "is_hidden", "first_seen_at", "updated_at"]


@router.get("/export")
async def export(user_id: UserId, format: Literal["json", "csv"] = "json") -> Response:
    data = [{k: r.get(k) for k in EXPORT_COLS} for r in await db.export_items(user_id)]
    if format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLS)
        w.writeheader()
        w.writerows(data)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"content-disposition": "attachment; filename=eztracker-items.csv"})
    return Response(json.dumps(data, default=str, indent=1), media_type="application/json",
                    headers={"content-disposition": "attachment; filename=eztracker-items.json"})
