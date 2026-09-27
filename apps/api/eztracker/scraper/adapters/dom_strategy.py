"""DOM fallback: read the rendered page when the JSON shape can't be identified.

Selectors are intentionally text/structure based (links, badges, line order) rather than CSS class
names, which a React build changes freely. Parsers are pure functions over `innerText` blocks so they
can be unit-tested from saved snapshots.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ...models import RawAssignment, RawCourse, RawNotification
from ...pipeline.dates import IST, resolve_relative, to_utc
from ..session import NexusSession
from .base import FetchHints, SchemaMismatch
from .json_strategy import PATHS, UUID, stable_notification_id

CATEGORY_BADGES = {"core", "soft skills", "elective"}
MODE_BADGES = {"in class", "hybrid", "online", "async"}
STATUS_PILLS = {"pending", "submitted", "overdue", "graded", "late", "completed", "missed", "evaluated"}
TYPE_BADGES = {"individual", "group", "team"}
NOTIF_CATEGORIES = {"assignment", "announcement", "course calendar", "general"}
RELATIVE_LABEL = re.compile(
    r"^(just now|now|today.*|yesterday.*|\d+\s*(s|m|min|h|hr|d|w)\w*\s*ago|"
    r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*|\d{1,2}\s+[a-z]{3,9}(\s+\d{4})?)$", re.I)

_JS_BLOCKS = """(sel) => Array.from(document.querySelectorAll(sel)).map(el => ({
  href: el.getAttribute('href') || el.querySelector('a')?.getAttribute('href') || null,
  text: el.innerText || '',
  unread: !!el.querySelector('[class*=unread], [class*=dot], [aria-label*=unread i]'),
}))"""


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def parse_course_block(text: str, term: str | None) -> RawCourse | None:
    lines = _lines(text)
    badges = [ln for ln in lines if ln.lower() in CATEGORY_BADGES | MODE_BADGES]
    rest = [ln for ln in lines if ln not in badges and not re.fullmatch(r"\d+%?|view|open", ln, re.I)]
    if not rest:
        return None
    category = next((b for b in badges if b.lower() in CATEGORY_BADGES), None)
    mode = next((b for b in badges if b.lower() in MODE_BADGES), None)
    instructor = rest[1] if len(rest) > 1 and len(rest[1]) < 60 else None
    return RawCourse(name=rest[0], instructor=instructor, category=category, mode=mode, term=term,
                     payload={"dom_text": text})


def parse_due_line(lines: list[str], now: datetime) -> datetime | None:
    for ln in lines:
        m = re.search(r"due[:\s]+(.+)$", ln, re.I)
        if m:
            d = resolve_relative(m.group(1), now)
            if d:
                # a due date shown without a time means end of that day in IST
                if not re.search(r"\d{1,2}:\d{2}|\b[ap]m\b", m.group(1), re.I):
                    local = d.astimezone(IST)
                    d = to_utc(local.replace(hour=23, minute=59))
                return d
    # due-date tile: two lines like "30" + "SEP"
    for a, b in zip(lines, lines[1:], strict=False):
        if re.fullmatch(r"\d{1,2}", a) and re.fullmatch(r"[A-Za-z]{3,9}", b):
            d = resolve_relative(f"{a} {b}", now)
            if d:
                return to_utc(d.astimezone(IST).replace(hour=23, minute=59))
    return None


def parse_assignment_block(href: str | None, text: str, base_url: str, now: datetime) -> RawAssignment | None:
    m = UUID.search(href or "")
    if not m:
        return None
    lines = _lines(text)
    status = next((ln for ln in lines if ln.lower() in STATUS_PILLS), None)
    type_raw = next((ln for ln in lines if ln.lower() in TYPE_BADGES), None)
    content = [ln for ln in lines if ln not in {status, type_raw}
               and not re.fullmatch(r"\d{1,2}|[A-Za-z]{3}", ln) and not re.match(r"due\b", ln, re.I)]
    if not content:
        return None
    title = content[0]
    course = content[1] if len(content) > 1 else None
    return RawAssignment(nexus_assignment_id=m.group(0), title=title, course_name_raw=course, type_raw=type_raw,
                         due_at=parse_due_line(lines, now), status_raw=status,
                         url=f"{base_url.rstrip('/')}/student/lms/assignments/{m.group(0)}",
                         payload={"dom_text": text})


def parse_notification_block(text: str, href: str | None, unread: bool, now: datetime) -> RawNotification | None:
    lines = _lines(text)
    if not lines:
        return None
    category = next((ln for ln in lines if ln.lower() in NOTIF_CATEGORIES), None)
    when = next((ln for ln in lines if RELATIVE_LABEL.match(ln)), None)
    content = [ln for ln in lines if ln not in {category, when}]
    if not content:
        return None
    title, snippet = content[0], " ".join(content[1:]) or None
    published = resolve_relative(when, now) if when else None
    return RawNotification(nexus_notification_id=stable_notification_id(title, snippet, published), title=title,
                           category_raw=category, snippet=snippet, published_at=published,
                           is_unread_on_nexus=unread, link_url=href, payload={"dom_text": text})


async def _blocks(session: NexusSession, selector: str) -> list[dict[str, Any]]:
    res: list[dict[str, Any]] = await session.page.evaluate(_JS_BLOCKS, selector)
    return res


class DomCourses:
    name = "dom"

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawCourse]:
        out: list[RawCourse] = []
        await session.goto(PATHS["courses"])
        for term in ["Pre-Term", "Term 1"]:
            tab = session.page.get_by_role("tab", name=re.compile(rf"^{term}", re.I)).first
            if await tab.count():
                await session.polite_pause()
                await tab.click()
                await session.page.wait_for_load_state("networkidle")
            for b in await _blocks(session, "a[href*='/student/lms/courses/'], [class*=card i]"):
                c = parse_course_block(b["text"], term)
                if c and not any(x.name == c.name for x in out):
                    m = re.search(r"/courses/([^/?#]+)", b["href"] or "")
                    c.nexus_course_id = m.group(1) if m else None
                    out.append(c)
        if not out:
            raise SchemaMismatch("no course cards found in DOM")
        return out


class DomAssignments:
    name = "dom"

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawAssignment]:
        now = datetime.now(UTC)
        await session.goto(PATHS["assignments"])
        await session.scroll_to_end()
        seen: set[str] = set()
        out: list[RawAssignment] = []
        for b in await _blocks(session, "a[href*='/student/lms/assignments/']"):
            a = parse_assignment_block(b["href"], b["text"], session.base_url, now)
            if a and a.nexus_assignment_id not in seen:
                seen.add(a.nexus_assignment_id)
                out.append(a)
        for a in out[:25]:
            if a.nexus_assignment_id in hints.detailed_ids and not hints.full_backfill:
                continue
            await session.goto(f"{PATHS['assignments']}/{a.nexus_assignment_id}")
            html = await session.page.evaluate(
                "() => (document.querySelector('main') || document.body).innerHTML")
            a.description_html = html[:100_000]
        return out


class DomNotifications:
    name = "dom"

    async def fetch(self, session: NexusSession, hints: FetchHints) -> list[RawNotification]:
        now = datetime.now(UTC)
        await session.goto(PATHS["notifications"])
        await session.scroll_to_end(max_rounds=40 if hints.full_backfill else 10)
        out: list[RawNotification] = []
        for b in await _blocks(session, "main li, main [role=listitem], main [class*=notification i]"):
            n = parse_notification_block(b["text"], b["href"], b["unread"], now)
            if n and not any(x.nexus_notification_id == n.nexus_notification_id for x in out):
                out.append(n)
        if not out:
            raise SchemaMismatch("no notification items found in DOM")
        return out
