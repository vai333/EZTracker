"""Completeness sweep, run after the three surfaces in every sync.

Nothing should be missed, so this pass visits the places the main surfaces don't cover:
  * every course page: full announcements (including ones that never produced a notification) and the
    course's own assignment list, unioned into My Work
  * My Work → Forms (`/forms/mine`)
  * the Calendar: dated events that look like deadlines or exams
  * a coverage audit: every list-bearing Nexus API response seen during the run is counted, and any
    endpoint EZTracker doesn't read yet is reported as a warning instead of being silently ignored
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from ..logs import log
from ..models import RawAssignment, RawCourse, RawNotification
from ..pipeline.classify import _DELIVERABLE
from .adapters.base import SchemaMismatch, as_text, best_list, iter_lists, pick
from .adapters.json_strategy import (
    _data,
    _parse_when,
    _strip_html,
    announcement_bodies,
    announcement_url,
    map_assignment,
)
from .session import NexusSession

API_HOST = "api-students.mesaschool.co.in"
_UUIDISH = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Endpoints EZTracker reads, and ones seen in discovery that are deliberately not work items
# (profile, course outline, study content). Keys have ids normalised to {id}.
READ = re.compile(r"^/api/v1/(curriculum/courses|curriculum/terms|assignments(/my)?|notifications|announcements|"
                  r"forms/mine|mrs/assessments)$")
MRS_COURSE_ID = "mesa-readiness-score"
MRS_PATH = "/student/lms/mesa-readiness-score"
IGNORED = re.compile(r"^/api/v1/(student/me|curriculum/courses/\{id\}|curriculum/topics|content/topics/.*|coach/.*)$")


@dataclass
class SweepResult:
    assignments: list[RawAssignment] = field(default_factory=list)       # extra items to union in
    notifications: list[RawNotification] = field(default_factory=list)   # orphan announcements, events
    courses: list[RawCourse] = field(default_factory=list)               # e.g. Mesa Readiness Score
    errors: list[dict[str, str]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)


def endpoint_key(url: str) -> str:
    p = urlsplit(url)
    return _UUIDISH.sub("{id}", p.path.rstrip("/"))


def key_shape(v: Any, depth: int = 0) -> Any:
    """Field names and types only — never values — so an unread endpoint can be mapped without seeing data."""
    if depth > 6:
        return "…"
    if isinstance(v, dict):
        return {k: key_shape(x, depth + 1) for k, x in list(v.items())[:40]}
    if isinstance(v, list):
        return [key_shape(v[0], depth + 1)] if v else []
    return "null" if v is None else type(v).__name__


def _list_size(body: Any) -> int:
    return max((len(lst) for lst in iter_lists(body)), default=0)


# --------------------------------------------------------------------------- mappers

def announcement_record(a: dict[str, Any], course_id: str, now: datetime) -> RawNotification | None:
    aid = as_text(a.get("id"))
    if not aid:
        return None
    body = as_text(a.get("body") or a.get("content") or a.get("description") or a.get("message") or a.get("html"))
    title = as_text(a.get("title")) or (_strip_html(body) or "")[:120] or "Announcement"
    return RawNotification(
        nexus_notification_id=f"ann:{aid}", title=title, category_raw="Announcement",
        snippet=(_strip_html(body) or "")[:500] or None,
        body_html=body if body and re.search(r"<\w+", body) else (f"<p>{body}</p>" if body else None),
        published_at=_parse_when(a.get("createdAt") or a.get("publishedAt") or pick(a, "published"), now),
        is_unread_on_nexus=None, link_url=announcement_url(aid),
        payload={"type": "announcement", "data": {"courseId": course_id, "announcementId": aid}, "announcement": a})


def form_record(o: dict[str, Any], base_url: str, now: datetime) -> RawAssignment | None:
    fid = as_text(o.get("id")) or as_text(pick(o, "id"))
    title = as_text(o.get("title")) or as_text(o.get("name")) or as_text(pick(o, "title"))
    if not fid or not title:
        return None
    due = _parse_when(o.get("dueAt") or o.get("closesAt") or o.get("deadline") or o.get("endDate")
                      or pick(o, "due"), now)
    submitted = bool(o.get("submitted") or o.get("isSubmitted") or o.get("mySubmissionStatus") == "submitted"
                     or o.get("responseId") or o.get("submittedAt"))
    return RawAssignment(
        nexus_assignment_id=f"form:{fid}", title=title, course_name_raw=as_text(o.get("courseTitle")),
        type_raw="Form", due_at=due, status_raw="Submitted" if submitted else "Pending",
        description_html=as_text(o.get("description")), url=f"{base_url.rstrip('/')}/student/lms/assignments",
        payload={**o, "courseId": o.get("courseId")})


def mrs_record(a: dict[str, Any], base_url: str) -> RawAssignment | None:
    """A Mesa Readiness Score assessment (`/api/v1/mrs/assessments`), linked to its own page by slug."""
    slug = as_text(a.get("slug"))
    title = as_text(a.get("title"))
    if not slug or not title:
        return None
    parts = a.get("partsSubmitted")
    status = as_text(a.get("status")) or ""
    done = (isinstance(parts, int) and parts >= 3) or status.lower() in {"completed", "submitted", "done", "scored"} \
        or a.get("mrsScore") is not None
    detail = []
    if isinstance(parts, int):
        detail.append(f"{parts} of 3 parts submitted")
    if a.get("mrsScore") is not None:
        detail.append(f"MRS score {a['mrsScore']} / {a.get('totalMarks')}")
    return RawAssignment(
        nexus_assignment_id=f"mrs:{slug}", title=title, course_name_raw="Mesa Readiness Score", type_raw="Assessment",
        due_at=None, status_raw="Submitted" if done else (status.title() or "Pending"),
        description_html="".join(f"<p>{x}</p>" for x in [as_text(a.get("blurb")), *detail] if x) or None,
        url=f"{base_url.rstrip('/')}{MRS_PATH}/{slug}", payload={**a, "courseId": MRS_COURSE_ID})


def event_record(e: dict[str, Any], now: datetime) -> RawNotification | None:
    """Calendar events become items only when they look like work (exam, deadline, submission…)."""
    eid = as_text(e.get("id"))
    title = as_text(e.get("title") or e.get("name") or e.get("summary"))
    start = _parse_when(e.get("startAt") or e.get("start") or e.get("startTime") or e.get("date")
                        or e.get("startDate"), now)
    if not eid or not title or not start:
        return None
    text = " ".join(x for x in (title, as_text(e.get("type")), as_text(e.get("category")),
                                as_text(e.get("description"))) if x)
    if not _DELIVERABLE.search(text):
        return None
    course_id = as_text(e.get("courseId")) or as_text((e.get("course") or {}).get("id")
                                                      if isinstance(e.get("course"), dict) else None)
    return RawNotification(
        nexus_notification_id=f"evt:{eid}", title=title, category_raw="Course Calendar",
        snippet=_strip_html(as_text(e.get("description"))), body_html=as_text(e.get("description")),
        published_at=now, is_unread_on_nexus=None,
        link_url=f"/student/lms/courses/{course_id}" if course_id else "/student/lms/calendar",
        payload={"type": "event", "data": {"courseId": course_id, "eventId": eid}, "_due_at": start.isoformat(),
                 "event": e})


# --------------------------------------------------------------------------- sweep

async def run_sweep(session: NexusSession, courses: list[RawCourse] | None,
                    assignments: list[RawAssignment] | None,
                    notifications: list[RawNotification] | None) -> SweepResult:
    res = SweepResult()
    now = datetime.now(UTC)
    also_read: set[str] = set()
    base = session.base_url
    known_assign = {a.nexus_assignment_id for a in assignments or []}
    notif_by_ann: dict[str, list[RawNotification]] = {}
    for n in notifications or []:
        ann = _data(n.payload).get("announcementId")
        if ann:
            notif_by_ann.setdefault(str(ann), []).append(n)

    # 1. every course page
    for c in courses or []:
        if not c.nexus_course_id:
            continue
        try:
            async with session.capture() as cap:
                await session.goto(f"/student/lms/courses/{c.nexus_course_id}")
        except Exception as e:  # noqa: BLE001 — one course failing must not stop the sweep
            res.errors.append({"surface": "sweep", "strategy": "json", "level": "warning",
                               "message": f"course page {c.name[:40]}: {str(e)[:120]}"})
            continue
        ok = [x for x in cap if 200 <= x.status < 300]
        ann_bodies = [x.body for x in ok if "/announcements" in x.url]
        full = announcement_bodies(ann_bodies)
        for aid, body in full.items():
            if aid in notif_by_ann:
                for n in notif_by_ann[aid]:
                    n.body_html = body
        for b in ann_bodies:
            for lst in iter_lists(b):
                for a in lst:
                    ann_id = as_text(a.get("id"))
                    if ann_id and ann_id not in notif_by_ann:
                        rec = announcement_record(a, c.nexus_course_id, now)
                        if rec:
                            res.notifications.append(rec)
                            notif_by_ann[ann_id] = [rec]
        for x in ok:
            if "/api/v1/assignments" in x.url and "courseId=" in x.url:
                try:
                    items = best_list([x.body], "assignments", threshold=1.5)
                except SchemaMismatch:
                    continue
                for o in items:
                    ra = map_assignment(o, base, now)
                    if ra and ra.nexus_assignment_id not in known_assign:
                        if "mySubmissionStatus" not in o:
                            ra.status_raw = None  # course list's `status` is the publish state, not yours
                        ra.payload = {**ra.payload, "courseId": o.get("courseId") or c.nexus_course_id,
                                      "_source": "course_page"}
                        ra.course_name_raw = ra.course_name_raw or c.name
                        res.assignments.append(ra)
                        known_assign.add(ra.nexus_assignment_id)

    # 2. forms + 3. calendar
    for path, kind in (("/student/lms/assignments", "forms"), ("/student/lms/calendar", "calendar")):
        try:
            async with session.capture() as cap:
                await session.goto(path)
                if kind == "forms":
                    tab = session.page.get_by_role("tab", name=re.compile(r"^Forms", re.I)).first
                    if await tab.count():
                        await session.polite_pause()
                        await tab.click()
                        await session.page.wait_for_load_state("networkidle")
        except Exception as e:  # noqa: BLE001
            res.errors.append({"surface": "sweep", "strategy": "json", "level": "warning",
                               "message": f"{kind}: {str(e)[:120]}"})
            continue
        for x in (y for y in cap if 200 <= y.status < 300 and API_HOST in y.url):
            if kind == "forms" and "/forms" in x.url:
                for lst in iter_lists(x.body):
                    for o in lst:
                        f = form_record(o, base, now)
                        if f and f.nexus_assignment_id not in known_assign:
                            res.assignments.append(f)
                            known_assign.add(f.nexus_assignment_id)
            if kind == "calendar" and not any(k in x.url for k in ("/notifications", "/student/me")):
                took = False
                for lst in iter_lists(x.body):
                    for evt in lst:
                        if isinstance(evt, dict) and (evt.get("startAt") or evt.get("start") or evt.get("startTime")):
                            took = True
                        ev = event_record(evt, now)
                        if ev:
                            res.notifications.append(ev)
                if took:
                    also_read.add(endpoint_key(x.url))

    # 4. lists that arrive with the app shell (seen on any page): term names, Mesa Readiness Score
    term_names: dict[str, str] = {}
    for x in session.captured:
        if API_HOST not in x.url or not (200 <= x.status < 300):
            continue
        k = endpoint_key(x.url)
        if k == "/api/v1/curriculum/terms":
            for lst in iter_lists(x.body):
                for t in lst:
                    if as_text(t.get("id")) and as_text(t.get("name")):
                        term_names[str(t["id"])] = str(t["name"])
        elif k == "/api/v1/mrs/assessments":
            for lst in iter_lists(x.body):
                for a in lst:
                    mrs = mrs_record(a, base)
                    if mrs and mrs.nexus_assignment_id not in known_assign:
                        res.assignments.append(mrs)
                        known_assign.add(mrs.nexus_assignment_id)
    for c in courses or []:
        tid = c.payload.get("termId")
        if tid and str(tid) in term_names:
            c.term = term_names[str(tid)]
    if any(a.nexus_assignment_id.startswith("mrs:") for a in res.assignments):
        res.courses.append(RawCourse(name="Mesa Readiness Score", nexus_course_id=MRS_COURSE_ID, category="Core",
                                     short_name="MRS", payload={"synthetic": True}))

    # 5. coverage audit over everything captured this run
    seen: Counter[str] = Counter()
    sizes: dict[str, int] = {}
    shapes: dict[str, Any] = {}
    for x in session.captured:
        if API_HOST not in x.url or not (200 <= x.status < 300):
            continue
        k = endpoint_key(x.url)
        seen[k] += 1
        sizes[k] = max(sizes.get(k, 0), _list_size(x.body))
        shapes.setdefault(k, key_shape(x.body))
    unread = [k for k in seen if sizes.get(k, 0) > 0 and k not in also_read
              and not READ.match(k) and not IGNORED.match(k)]
    res.coverage = {
        "endpoints": {k: {"calls": seen[k], "max_items": sizes.get(k, 0)} for k in sorted(seen)},
        "unread_endpoints": sorted(unread),
        "unread_shapes": {k: shapes.get(k) for k in sorted(unread)},
        "course_pages": len([c for c in courses or [] if c.nexus_course_id]),
        "orphan_announcements": sum(1 for n in res.notifications if n.nexus_notification_id.startswith("ann:")),
        "course_only_assignments": sum(1 for a in res.assignments if a.payload.get("_source") == "course_page"),
        "forms": sum(1 for a in res.assignments if a.nexus_assignment_id.startswith("form:")),
        "calendar_items": sum(1 for n in res.notifications if n.nexus_notification_id.startswith("evt:")),
        "mrs_assessments": sum(1 for a in res.assignments if a.nexus_assignment_id.startswith("mrs:")),
    }
    for k in unread:
        res.errors.append({"surface": "coverage", "strategy": "audit", "level": "warning",
                           "message": f"Nexus returned a list EZTracker doesn't read yet: {k} "
                                      f"({sizes[k]} items) — check docs/nexus_api_map.md"})
    log.info("sweep_done", **{k: v for k, v in res.coverage.items() if k != "endpoints"})
    return res
