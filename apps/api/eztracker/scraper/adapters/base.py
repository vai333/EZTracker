"""Adapter protocol + tolerant JSON field extraction shared by the JSON strategy.

Until docs/nexus_api_map.md pins exact endpoints, the JSON strategy finds the right list inside whatever
the SPA fetched by scoring candidate arrays on the keys their objects carry. Field lookups try several
common spellings (camelCase, snake_case, nested objects).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from ...models import RawRecord
from ..session import NexusSession

Surface = Literal["courses", "assignments", "notifications"]


class SchemaMismatch(RuntimeError):
    """The JSON we saw doesn't look like this surface — fall back to DOM."""


@dataclass
class FetchHints:
    known_ids: set[str] = field(default_factory=set)    # ext ids already stored (incremental stop / detail skip)
    detailed_ids: set[str] = field(default_factory=set)  # assignments whose detail body we already have
    full_backfill: bool = False


class Strategy(Protocol):
    name: str

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[Any]: ...


class Adapter(Protocol):
    surface: Surface

    async def fetch(self, session: NexusSession) -> list[RawRecord]: ...


# --------------------------------------------------------------------------- pinned endpoints

ENDPOINTS_FILE = Path(__file__).resolve().parents[1] / "endpoints.json"


def pinned(surface: str) -> dict[str, Any] | None:
    """Endpoint hints written after discovery: {"assignments": {"url_contains": "/api/assignments"}}."""
    if ENDPOINTS_FILE.exists():
        data: dict[str, Any] = json.loads(ENDPOINTS_FILE.read_text())
        v = data.get(surface)
        return v if isinstance(v, dict) else None
    return None


# --------------------------------------------------------------------------- field extraction

KEYS: dict[str, list[str]] = {
    "id": ["id", "_id", "uuid", "assignmentId", "assignment_id", "notificationId", "notification_id",
           "courseId", "course_id"],
    "title": ["title", "name", "assignmentName", "assignment_name", "heading", "subject", "assignmentTitle"],
    "course_name": ["courseTitle", "courseName", "course_name", "course.name", "course.title", "course.courseName",
                    "courseTitle", "subjectName"],
    "course_id": ["courseId", "course_id", "course.id", "course._id"],
    "due": ["dueDate", "due_date", "dueAt", "due_at", "deadline", "endDate", "end_date", "submissionDeadline",
            "submission_deadline", "closeDate", "close_date", "dueDateTime", "due"],
    "status": ["mySubmissionStatus", "status", "submissionStatus", "submission_status", "state", "submission.status"],
    "type": ["type", "assignmentType", "assignment_type", "submissionType", "submission_type", "groupType",
             "workType"],
    "description": ["description", "instructions", "details", "body", "content", "descriptionHtml",
                    "description_html", "html"],
    "attachments": ["attachments", "files", "resources", "documents", "materials"],
    "message": ["message", "body", "content", "description", "text", "snippet", "summary", "preview"],
    "category": ["category", "type", "notificationType", "notification_type", "tag", "kind", "module"],
    "published": ["createdAt", "created_at", "publishedAt", "published_at", "timestamp", "date", "sentAt",
                  "sent_at", "time", "updatedAt"],
    "read": ["isRead", "read", "is_read", "seen", "isSeen", "readAt", "read_at"],
    "link": ["link", "url", "redirectUrl", "redirect_url", "actionUrl", "action_url", "href", "path", "route"],
    "instructor": ["instructor", "instructorName", "instructor_name", "faculty", "facultyName", "teacher",
                   "teacherName", "instructors", "faculties", "teachers", "professor"],
    "course_category": ["courseType", "category", "courseCategory", "course_category", "course_type", "tag",
                        "tags", "badge"],
    "mode": ["classType", "mode", "deliveryMode", "delivery_mode", "classMode", "class_mode", "format"],
    "term": ["term", "termName", "term_name", "semester", "phase", "term.name"],
}


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def pick(obj: dict[str, Any], field_name: str) -> Any:
    for k in KEYS[field_name]:
        v = get_path(obj, k)
        if v not in (None, "", [], {}):
            return v
    return None


def as_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        return as_text(v.get("name") or v.get("title") or v.get("label") or v.get("fullName"))
    if isinstance(v, list):
        parts = [as_text(x) for x in v]
        return ", ".join(p for p in parts if p) or None
    return str(v)


def iter_lists(obj: Any, depth: int = 0) -> list[list[dict[str, Any]]]:
    """All arrays-of-objects anywhere inside a JSON document."""
    out: list[list[dict[str, Any]]] = []
    if depth > 6:
        return out
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:5]):
            out.append(obj)
        for x in obj[:3]:
            out.extend(iter_lists(x, depth + 1))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(iter_lists(v, depth + 1))
    return out


SURFACE_SIGNATURE: dict[str, list[tuple[str, float]]] = {
    "assignments": [("title", 1.0), ("due", 2.0), ("status", 0.5), ("course_name", 1.0), ("type", 0.3)],
    "notifications": [("title", 0.5), ("message", 1.0), ("published", 1.5), ("read", 1.5), ("category", 0.5)],
    "courses": [("title", 1.0), ("instructor", 2.0), ("course_category", 1.0), ("mode", 1.0), ("term", 0.5)],
}


def score_list(items: list[dict[str, Any]], surface: str) -> float:
    sample = items[:5]
    score = 0.0
    for fname, w in SURFACE_SIGNATURE[surface]:
        hits = sum(1 for it in sample if pick(it, fname) is not None)
        score += w * hits / len(sample)
    return score


def best_list(bodies: list[Any], surface: str, threshold: float = 2.0) -> list[dict[str, Any]]:
    """Merge all qualifying arrays (pagination produces several) for the best-scoring shape."""
    scored = [(score_list(lst, surface), lst) for b in bodies for lst in iter_lists(b)]
    scored = [x for x in scored if x[0] >= threshold]
    if not scored:
        raise SchemaMismatch(f"no JSON array looks like {surface}")
    top = max(s for s, _ in scored)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s, lst in scored:
        if s < top - 0.75:
            continue
        for it in lst:
            key = str(pick(it, "id") or json.dumps(it, sort_keys=True, default=str)[:200])
            if key not in seen:
                seen.add(key)
                merged.append(it)
    return merged


def lists_per_body(bodies: list[Any], surface: str, threshold: float = 2.0) -> list[dict[str, Any]]:
    """Judge each API response on its own and keep every qualifying list, de-duplicated by id.

    `best_list` across all responses would drop a page whose objects look slightly different (e.g. a term
    whose course has no instructor) — a silent miss. Per-response selection never discards a whole response.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for body in bodies:
        try:
            items = best_list([body], surface, threshold)
        except SchemaMismatch:
            continue
        for it in items:
            key = str(pick(it, "id") or json.dumps(it, sort_keys=True, default=str)[:200])
            if key not in seen:
                seen.add(key)
                out.append(it)
    if not out:
        raise SchemaMismatch(f"no JSON array looks like {surface}")
    return out
