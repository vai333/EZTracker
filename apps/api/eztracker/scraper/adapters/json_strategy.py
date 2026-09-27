"""JSON strategy: let the Nexus pages make their own API calls, capture the responses, map the objects.

The scraper never holds Nexus's access token: the SPA attaches it to its own requests to
api-students.mesaschool.co.in, and we only read the JSON that comes back (docs/nexus_api_map.md).
Mappers understand Nexus's exact field names first and fall back to tolerant key lookup.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from typing import Any

from ...models import RawAssignment, RawCourse, RawNotification
from ...pipeline.dates import parse_absolute, resolve_relative
from ..session import CapturedResponse, NexusSession
from .base import FetchHints, SchemaMismatch, as_text, iter_lists, lists_per_body, pick, pinned

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

PATHS = {
    "courses": "/student/lms/courses",
    "assignments": "/student/lms/assignments",
    "notifications": "/student/lms/notifications",
}

# Nexus notification `type` → the tab it appears under in the Nexus UI
NOTIFICATION_CATEGORY = {
    "announcement": "Announcement",
    "assignment_new": "Assignment",
    "assignment_updated": "Assignment",
    "assignment_graded": "Assignment",
    "assignment_due": "Assignment",
    "graded": "Assignment",
    "reply": "Announcement",
    "attendance": "General",
    "event": "Course Calendar",
    "event_updated": "Course Calendar",
    "system": "General",
    "ticket_update": "General",
}


def _pin_filter(captured: list[CapturedResponse], surface: str) -> list[CapturedResponse]:
    pin = pinned(surface)
    ok = [c for c in captured if 200 <= c.status < 300]
    if pin and pin.get("url_contains"):
        matched = [c for c in ok if pin["url_contains"] in c.url]
        return matched or ok  # if Nexus renamed the endpoint, fall back to scoring everything
    return ok


def _bodies(captured: list[CapturedResponse], surface: str) -> list[Any]:
    return [c.body for c in _pin_filter(captured, surface)]


def _parse_when(v: Any, scraped_at: datetime) -> datetime | None:
    return parse_absolute(v) if not isinstance(v, str) or re.search(r"\d{4}-\d{2}-\d{2}|^\d{10,13}$", v) \
        else resolve_relative(v, scraped_at)


def _strip_html(s: str | None) -> str | None:
    if not s:
        return None
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
    return t or None


async def _click_tab(session: NexusSession, label: str) -> bool:
    # Nexus tab buttons carry extra text (counts/icons), so match the label as a prefix, never exactly
    pattern = re.compile(rf"^\s*{re.escape(label)}\b", re.I)
    loc = session.page.get_by_role("tab", name=pattern).first
    if await loc.count() == 0:
        loc = session.page.get_by_role("button", name=pattern).first
    if await loc.count() == 0:
        loc = session.page.get_by_text(pattern).first
    if await loc.count() == 0:
        return False
    await session.polite_pause()
    await loc.click()
    await session.page.wait_for_load_state("networkidle")
    return True


# --------------------------------------------------------------------------- mappers (pure, unit-tested)

def map_course(o: dict[str, Any], term: str | None = None) -> RawCourse | None:
    name = as_text(o.get("title")) or as_text(pick(o, "title"))
    if not name:
        return None
    return RawCourse(
        name=name,
        nexus_course_id=as_text(o.get("id")) or as_text(pick(o, "id")),
        instructor=as_text(o.get("instructorName")) if "instructorName" in o else as_text(pick(o, "instructor")),
        category=as_text(o.get("courseType")) or as_text(pick(o, "course_category")),
        mode=as_text(o.get("classType")) or as_text(pick(o, "mode")),
        term=term or as_text(pick(o, "term")),
        short_name=as_text(o.get("shortName")),
        visible=o.get("visible") is not False,
        payload=o,
    )


def _materials(o: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for a in (o.get("materials") if isinstance(o.get("materials"), list) else pick(o, "attachments")) or []:
        if isinstance(a, dict):
            url = as_text(a.get("url") or a.get("link") or a.get("fileUrl") or a.get("href"))
            if url:
                out.append({"name": as_text(a.get("title") or a.get("fileName") or a.get("name")) or "Attachment",
                            "url": url})
        elif isinstance(a, str) and a.startswith("http"):
            out.append({"name": a.rsplit("/", 1)[-1], "url": a})
    return out


def map_assignment(o: dict[str, Any], base_url: str, scraped_at: datetime) -> RawAssignment | None:
    ext = as_text(o.get("id")) or as_text(pick(o, "id"))
    title = as_text(o.get("title")) or as_text(pick(o, "title"))
    if not ext or not title:
        return None
    status: str | None
    desc: str | None
    kind: str | None
    if "mySubmissionStatus" in o:  # Nexus /assignments/my shape
        status = "Submitted" if (o.get("mySubmissionStatus") or "").lower() == "submitted" else "Pending"
        parts = [x for x in (o.get("description"), o.get("instructions")) if x]
        desc = "\n".join(parts) or None
        kind = "Group" if o.get("isGroup") else "Individual"
        course = as_text(o.get("courseTitle"))
        due = _parse_when(o.get("dueAt"), scraped_at)
    else:
        status = as_text(pick(o, "status"))
        desc = as_text(pick(o, "description"))
        kind = as_text(pick(o, "type"))
        course = as_text(pick(o, "course_name"))
        due = _parse_when(pick(o, "due"), scraped_at)
    return RawAssignment(
        nexus_assignment_id=ext, title=title, course_name_raw=course, type_raw=kind, due_at=due,
        status_raw=status, description_html=desc, attachments=_materials(o),
        url=f"{base_url.rstrip('/')}/student/lms/assignments/{ext}", payload=o)


def _data(o: dict[str, Any]) -> dict[str, Any]:
    d = o.get("data")
    return d if isinstance(d, dict) else {}


def announcement_url(announcement_id: str) -> str:
    return f"/student/community/{announcement_id}?src=notification"


def _notification_link(ntype: str, data: dict[str, Any]) -> str | None:
    """Exactly where Nexus's own notification click handler navigates (recorded from its front-end code)."""
    course = data.get("courseId") or data.get("course_id")
    assignment = data.get("assignmentId") or data.get("assignment_id")
    announcement = data.get("announcementId") or data.get("announcement_id")
    if ntype == "system" and data.get("subtype") == "calendar_event":
        return "/student/lms/calendar"
    if ntype in ("announcement", "reply"):
        if announcement:
            return announcement_url(str(announcement))
        return f"/student/lms/courses/{course}" if course else None
    if ntype in ("assignment_new", "assignment_due"):
        if assignment:
            return f"/student/lms/assignments/{assignment}"
        return f"/student/lms/courses/{course}" if course else None
    if ntype == "graded" and assignment:
        return f"/student/lms/assignments/{assignment}"
    return as_text(data.get("url")) or None


def map_notification(o: dict[str, Any], scraped_at: datetime) -> RawNotification | None:
    title = as_text(o.get("title")) or as_text(pick(o, "title"))
    msg = as_text(o.get("body")) if "body" in o else as_text(pick(o, "message"))
    if not title and not msg:
        return None
    published = _parse_when(o.get("createdAt") or pick(o, "published"), scraped_at)
    ext = as_text(o.get("id")) or as_text(pick(o, "id")) or stable_notification_id(title, msg, published)
    data = _data(o)
    ntype = as_text(o.get("type")) or ""
    if "isRead" in o:
        unread: bool | None = not bool(o["isRead"])
    else:
        read = pick(o, "read")
        unread = (not bool(read)) if read is not None else None
    if ntype == "system" and data.get("subtype") == "calendar_event":
        ntype_cat: str | None = "Course Calendar"
    else:
        ntype_cat = NOTIFICATION_CATEGORY.get(ntype)
    category = ntype_cat or ("Course Calendar" if "event" in ntype else None) \
        or as_text(pick(o, "category"))
    return RawNotification(
        nexus_notification_id=ext, title=title, category_raw=category,
        snippet=(_strip_html(msg) or "")[:500] or None,
        body_html=msg if msg and re.search(r"<\w+", msg) else None,
        published_at=published, is_unread_on_nexus=unread,
        link_url=_notification_link(ntype, data) or as_text(pick(o, "link")), payload=o)


def stable_notification_id(title: str | None, snippet: str | None, published: datetime | None) -> str:
    """Nexus notifications without an id get a stable hash so re-scrapes dedupe (§4)."""
    day = published.astimezone(UTC).strftime("%Y-%m-%d") if published else ""
    return "h_" + hashlib.sha256(f"{title}|{snippet}|{day}".encode()).hexdigest()[:24]


def announcement_bodies(bodies: list[Any]) -> dict[str, str]:
    """{announcementId: full html/text} from /announcements?courseId= responses (tolerant: shape unrecorded)."""
    out: dict[str, str] = {}
    for b in bodies:
        for lst in iter_lists(b):
            for a in lst:
                aid = as_text(a.get("id"))
                text = as_text(a.get("body") or a.get("content") or a.get("description") or a.get("message")
                               or a.get("html"))
                if aid and text:
                    title = as_text(a.get("title"))
                    out[aid] = f"<h3>{title}</h3>{text}" if title and title not in text else text
    return out


# --------------------------------------------------------------------------- strategies

class JsonCourses:
    name = "json"
    terms = ("Pre-Term", "Term 1", "Term 2", "Term 3")

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawCourse]:
        out: dict[str, RawCourse] = {}

        def take(bucket: list[CapturedResponse], term: str | None) -> None:
            try:
                items = lists_per_body(_bodies(bucket, "courses"), "courses", threshold=1.0)
            except SchemaMismatch:
                return
            for o in items:
                c = map_course(o, term)
                if c:
                    key = c.nexus_course_id or c.name
                    if key not in out or (term and not out[key].term):
                        out[key] = c

        async with session.capture() as first:
            await session.goto(PATHS["courses"])
        take(first, None)
        for t in self.terms:
            async with session.capture() as bucket:
                clicked = await _click_tab(session, t)
            if clicked:
                take(bucket, t)
        # the initial (default-tab) load has no label: infer it from termIds seen under a named tab
        term_by_id = {c.payload.get("termId"): c.term for c in out.values() if c.term and c.payload.get("termId")}
        for c in out.values():
            if not c.term:
                c.term = term_by_id.get(c.payload.get("termId"))
        if not out:
            raise SchemaMismatch("course list empty")
        return list(out.values())


class JsonAssignments:
    name = "json"

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawAssignment]:
        now = datetime.now(UTC)
        async with session.capture() as cap:
            await session.goto(PATHS["assignments"])
            await session.scroll_to_end()
        # /assignments/my carries description, instructions and materials: no detail pages needed
        items = [a for a in (map_assignment(o, session.base_url, now)
                             for o in lists_per_body(_bodies(cap, "assignments"), "assignments")) if a]
        return items


class JsonNotifications:
    name = "json"

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawNotification]:
        now = datetime.now(UTC)
        async with session.capture() as bucket:
            await session.goto(PATHS["notifications"])
            # Always page to the very end (hasMore=false): nothing is skipped, and the feed is small.
            for _ in range(60):
                await session.scroll_to_end(max_rounds=2)
                more = session.page.get_by_role("button", name=re.compile(r"(load|show|view) more", re.I)).first
                if await more.count():
                    await session.polite_pause()
                    await more.click()
                    await session.page.wait_for_load_state("networkidle")
                elif not self._has_more(bucket):
                    break
        # full announcement text is filled in by the course-page sweep (scraper/sweep.py)
        return [n for n in (map_notification(o, now)
                            for o in lists_per_body(_bodies(bucket, "notifications"), "notifications")) if n]

    @staticmethod
    def _has_more(bucket: list[CapturedResponse]) -> bool:
        for c in reversed(bucket):
            if isinstance(c.body, dict) and isinstance(c.body.get("data"), dict) and "hasMore" in c.body["data"]:
                return bool(c.body["data"]["hasMore"])
        return False
