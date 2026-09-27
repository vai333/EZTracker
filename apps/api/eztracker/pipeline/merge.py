"""raw → work_items. Implements §6 steps 2–8 over an in-memory State, recording a ChangeSet.

Sticky rules (non-negotiable):
  * classification == 'manual'      → scraper never changes course_id / classification
  * my_status_set_by == 'user'      → scraper never changes my_status
  * due_source == 'user'            → scraper never changes due_at (records upstream_due_at + event instead)
  * title_source / kind_source=user → scraper never changes title / kind
  * is_hidden                       → stays hidden unless the upstream due date changes (then unhide + badge)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from ..models import (
    Alias,
    AssignmentRow,
    ChangeSet,
    Course,
    Event,
    NotificationRow,
    RawAssignment,
    RawCourse,
    RawNotification,
    State,
    WorkItem,
    new_id,
)
from .classify import Classifier, default_classifier, kind_for_assignment
from .dates import extract_due, parse_absolute
from .normalize import (
    KNOWN_CASE_COMPANIES,
    assignment_hash,
    category_of,
    course_core_name,
    default_short_name,
    notification_display_title,
    notification_hash,
    seed_aliases,
)
from .text import html_to_markdown, normalize

PALETTE_SIZE = 8

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# Routes verified to exist in Nexus (docs/nexus_api_map.md). Anything else would 404.
_KNOWN_ROUTES = re.compile(
    rf"^/student/(lms(/(courses|assignments|notifications|calendar|attendance)(/{_UUID})?"
    rf"|/mesa-readiness-score(/[a-z0-9-]{{1,60}})?)?"
    rf"|community/[A-Za-z0-9_-]{{6,64}})/?(\?[\w=&%.-]*)?$", re.I)
_LIST_FOR = {"assignments": "/student/lms/assignments", "courses": "/student/lms/courses"}


def safe_nexus_url(base: str, url: str | None, fallback_path: str) -> str:
    """A deep link that is guaranteed to open in Nexus: verified route + real UUID, else the list page."""
    for candidate in (url, fallback_path):
        if not candidate:
            continue
        path = candidate[len(base):] if candidate.startswith(base) else candidate
        if not path.startswith("/"):
            continue
        if _KNOWN_ROUTES.match(path):
            return base + path
        # a detail route with a non-UUID id (e.g. fixture ids) → fall back to that section's list page
        m = re.match(r"^/student/lms/(assignments|courses)/", path)
        if m:
            return base + _LIST_FOR[m.group(1)]
    return base + "/student/lms/notifications"


@dataclass
class Fetched:
    courses: list[RawCourse] | None = None          # None = surface failed; skip, don't wipe
    assignments: list[RawAssignment] | None = None
    notifications: list[RawNotification] | None = None


@dataclass
class SyncStats:
    courses: int = 0
    courses_new: int = 0
    assignments_new: int = 0
    notifications_new: int = 0
    changed: int = 0
    needs_review: int = 0
    linked: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"courses": self.courses, "courses_new": self.courses_new,
                "assignments_new": self.assignments_new, "notifications_new": self.notifications_new,
                "changed": self.changed, "needs_review": self.needs_review, "linked": self.linked, **self.extra}


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


class Pipeline:
    def __init__(self, state: State, now: datetime, nexus_base_url: str,
                 classifier: Classifier | None = None) -> None:
        self.s = state
        self.now = now
        self.base = nexus_base_url.rstrip("/")
        self.cs = ChangeSet()
        self.stats = SyncStats()
        self.classifier = classifier or default_classifier()

    # ------------------------------------------------------------------ helpers

    def _update(self, wi: WorkItem, **fields: Any) -> dict[str, Any]:
        """Set fields on a work item, recording only real changes. Returns {field: old} of changes."""
        changed: dict[str, Any] = {}
        for k, v in fields.items():
            old = getattr(wi, k)
            if old != v:
                changed[k] = old
                setattr(wi, k, v)
        if changed:
            if wi.id in self.cs.work_items_insert:
                self.cs.work_items_insert[wi.id] = wi
            else:
                self.cs.work_items_update.setdefault(wi.id, {}).update({k: getattr(wi, k) for k in changed})
        return changed

    def _event(self, wi: WorkItem, event: str, frm: Any = None, to: Any = None) -> None:
        self.cs.events.append(Event(wi.id, "scraper", event, _jsonable(frm), _jsonable(to)))

    def _insert_item(self, wi: WorkItem) -> None:
        self.s.work_items[wi.id] = wi
        self.cs.work_items_insert[wi.id] = wi
        self._event(wi, "created", None, {"title": wi.title, "course_id": wi.course_id})
        if wi.course_id is None and wi.classification == "unresolved":
            self.stats.needs_review += 1

    def _add_alias(self, course_id: str, alias: str, source: str = "seed", weight: float = 1.0) -> None:
        alias = alias.lower().strip()
        if not alias or any(a.alias == alias for a in self.s.aliases_for(course_id)):
            return
        a = Alias(new_id(), course_id, alias, source, weight)
        self.s.aliases[a.id] = a
        self.cs.aliases_insert[a.id] = a

    def _resolve_course(self, course_name_raw: str | None) -> tuple[str | None, float]:
        if not course_name_raw:
            return None, 0.0
        target = normalize(course_name_raw)
        target_core = normalize(course_core_name(course_name_raw))
        best: tuple[str | None, float] = (None, 0.0)
        for c in self.s.courses.values():
            if normalize(c.name) == target:
                return c.id, 1.0
            if target_core and normalize(course_core_name(c.name)) == target_core:
                best = (c.id, 1.0)
            elif best[1] < 1.0:
                sim = fuzz.token_set_ratio(target_core, normalize(course_core_name(c.name)))
                if sim >= 92 and sim / 100 * 0.9 > best[1]:
                    best = (c.id, round(sim / 100 * 0.9, 3))
        return best

    def _nexus_link(self, url: str | None, fallback_path: str) -> list[dict[str, str]]:
        return [{"label": "Open in Nexus", "url": safe_nexus_url(self.base, url, fallback_path)}]

    # ------------------------------------------------------------------ step 2: courses

    def sync_courses(self, raws: list[RawCourse], assignments: list[RawAssignment] | None) -> None:
        titles_by_course: dict[str, list[str]] = {}
        for a in assignments or []:
            titles_by_course.setdefault(normalize(a.course_name_raw), []).append(a.title)
        all_names = [r.name for r in raws] + [c.name for c in self.s.courses.values()]
        for r in raws:
            self.stats.courses += 1
            existing = next((c for c in self.s.courses.values()
                             if (r.nexus_course_id and c.nexus_course_id == r.nexus_course_id)
                             or normalize(c.name) == normalize(r.name)), None)
            fields: dict[str, Any] = {"name": r.name, "instructor": r.instructor, "category": category_of(r.category),
                      "mode": r.mode, "term": r.term}
            if r.nexus_course_id:
                fields["nexus_course_id"] = r.nexus_course_id
            if existing:
                if any(getattr(existing, k) != v for k, v in fields.items()):
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    self.cs.courses_upsert[existing.id] = existing
                continue
            c = Course(id=new_id(), short_name=r.short_name or default_short_name(r.name),
                       color_index=len(self.s.courses) % PALETTE_SIZE, is_archived=not r.visible, **fields)
            self.s.courses[c.id] = c
            self.cs.courses_upsert[c.id] = c
            self.stats.courses_new += 1
            for alias, w in seed_aliases(r, all_names, titles_by_course.get(normalize(r.name), [])):
                self._add_alias(c.id, alias, "seed", w)

    # ------------------------------------------------------------------ steps 3 + 5: assignments

    def sync_assignments(self, raws: list[RawAssignment]) -> None:
        for r in raws:
            h = assignment_hash(r)
            row = self.s.assignment_by_ext(r.nexus_assignment_id)
            if row and row.content_hash == h and any(
                    w.assignment_raw_id == row.id for w in self.s.work_items.values()):
                self.cs.assignments_touch.add(row.id)
                continue
            if row is None:
                row = AssignmentRow(id=new_id(), nexus_assignment_id=r.nexus_assignment_id, title=r.title,
                                    content_hash=h)
                self.s.assignments[row.id] = row
                self.stats.assignments_new += 1
            for k in ("title", "course_name_raw", "type_raw", "due_at", "status_raw", "description_html",
                      "attachments", "url", "payload"):
                setattr(row, k, getattr(r, k))
            row.content_hash = h
            self.cs.assignments_upsert[row.id] = row
            self._merge_assignment(row)

    def _merge_assignment(self, row: AssignmentRow) -> None:
        # Nexus gives an exact courseId on each assignment; fall back to matching the course name
        ext_course = (row.payload or {}).get("courseId")
        by_id = next((c.id for c in self.s.courses.values() if ext_course and c.nexus_course_id == ext_course), None)
        course_id, conf = (by_id, 1.0) if by_id else self._resolve_course(row.course_name_raw)
        submitted = normalize(row.status_raw) in {"submitted", "completed", "graded", "evaluated", "done"}
        links = self._nexus_link(row.url, f"/student/lms/assignments/{row.nexus_assignment_id}")
        links += [{"label": a.get("name") or "Attachment", "url": a["url"]}
                  for a in row.attachments if a.get("url")]
        instructions = html_to_markdown(row.description_html)
        wi = next((w for w in self.s.work_items.values() if w.assignment_raw_id == row.id), None)

        if course_id:
            blob = normalize(row.title)
            for co in KNOWN_CASE_COMPANIES:
                if re.search(rf"(?<!\w){re.escape(co)}(?!\w)", blob):
                    self._add_alias(course_id, co)

        if wi is None:
            wi = WorkItem(
                id=new_id(), title=row.title, origin="assignments_tab",
                kind=kind_for_assignment(row.title, row.type_raw), course_id=course_id,
                due_at=row.due_at, due_source="nexus_field" if row.due_at else None,
                instructions_md=instructions, links=links, nexus_status=row.status_raw,
                my_status="submitted" if submitted else "pending",
                classification="auto" if course_id else "unresolved", confidence=conf or None,
                classifier_reasons=[{"course_id": course_id, "course": row.course_name_raw, "score": conf,
                                     "reasons": [f"My Work course '{row.course_name_raw}'"]}] if course_id else [],
                assignment_raw_id=row.id,
            )
            self._insert_item(wi)
            return
        self._diff_scraper_fields(wi, title=row.title, due_at=row.due_at, due_source="nexus_field",
                                  nexus_status=row.status_raw, instructions_md=instructions, links=links,
                                  kind=kind_for_assignment(row.title, row.type_raw))
        if wi.classification != "manual" and course_id and wi.course_id != course_id:
            old = wi.course_id
            self._update(wi, course_id=course_id, classification="auto", confidence=conf)
            self._event(wi, "moved", old, course_id)
        if submitted and wi.my_status_set_by != "user" and wi.my_status != "submitted":
            old = wi.my_status
            self._update(wi, my_status="submitted")
            self._event(wi, "status_changed", old, "submitted")

    # ------------------------------------------------------------------ step 7 + 8: diff with sticky rules

    def _diff_scraper_fields(self, wi: WorkItem, *, title: str, due_at: datetime | None, due_source: str,
                             instructions_md: str | None, links: list[dict[str, str]],
                             kind: str, nexus_status: str | None = None,
                             track_status: bool = True) -> None:
        before = len(self.cs.events)
        old: Any
        if wi.title_source != "user" and title and wi.title != title:
            old = wi.title
            self._update(wi, title=title)
            self._event(wi, "title_changed", old, title)
        if wi.kind_source != "user" and wi.kind != kind:
            self._update(wi, kind=kind)
        if wi.due_source == "user":
            if due_at is not None and wi.upstream_due_at != due_at:
                old = wi.upstream_due_at
                self._update(wi, upstream_due_at=due_at)
                self._event(wi, "due_changed_upstream", old, due_at)
        elif wi.due_at != due_at and due_at is not None:
            old = wi.due_at
            self._update(wi, due_at=due_at, due_source=due_source,
                         due_changed_at=self.now if old is not None else wi.due_changed_at)
            self._event(wi, "due_changed", old, due_at)
            if wi.is_hidden:
                self._update(wi, is_hidden=False, upstream_updated_at=self.now)
                self._event(wi, "unhidden", True, False)
        if track_status and wi.nexus_status != nexus_status:
            old = wi.nexus_status
            self._update(wi, nexus_status=nexus_status)
            self._event(wi, "nexus_status_changed", old, nexus_status)
        if instructions_md and wi.instructions_md != instructions_md:
            self._update(wi, instructions_md=instructions_md)
            self._event(wi, "instructions_changed", None, None)
        if wi.links != links:
            # keep user-irrelevant link churn silent, but never drop the Open-in-Nexus link
            self._update(wi, links=links)
        if len(self.cs.events) > before:
            self.stats.changed += 1

    # ------------------------------------------------------------------ steps 4 + 6: notifications

    def sync_notifications(self, raws: list[RawNotification]) -> None:
        for r in raws:
            h = notification_hash(r)
            row = self.s.notification_by_ext(r.nexus_notification_id)
            linked_items = [w for (w, nid) in self.s.sources if row and nid == row.id]
            if row and row.content_hash == h and linked_items:
                self.cs.notifications_touch.add(row.id)
                continue
            if row is None:
                row = NotificationRow(id=new_id(), nexus_notification_id=r.nexus_notification_id, content_hash=h)
                self.s.notifications[row.id] = row
                self.stats.notifications_new += 1
            for k in ("title", "category_raw", "snippet", "body_html", "published_at", "is_unread_on_nexus",
                      "link_url", "payload"):
                setattr(row, k, getattr(r, k))
            row.content_hash = h
            self.cs.notifications_upsert[row.id] = row

            if linked_items:
                self._refresh_from_notification(row, linked_items)
            else:
                self._classify_new(row)

    def _notification_fields(self, row: NotificationRow) -> dict[str, Any]:
        title = notification_display_title(row.title, row.snippet)
        instructions = html_to_markdown(row.body_html) or (row.snippet or None)
        text = " ".join(x for x in [row.title, row.snippet, re.sub(r"<[^>]+>", " ", row.body_html or "")] if x)
        # calendar events carry their own date; everything else is parsed from the text
        explicit = parse_absolute((row.payload or {}).get("_due_at"))
        return {"title": title, "instructions_md": instructions,
                "due_at": explicit or extract_due(text, row.published_at),
                "links": self._nexus_link(row.link_url, "/student/lms/notifications")}

    def _refresh_from_notification(self, row: NotificationRow, item_ids: list[str]) -> None:
        f = self._notification_fields(row)
        for wid in item_ids:
            wi = self.s.work_items.get(wid)
            if wi is None or wi.origin != "notification_only":
                continue
            primary = min((nid for (w, nid) in self.s.sources if w == wid),
                          key=lambda nid: (self.s.notifications[nid].published_at or self.now, nid)
                          if nid in self.s.notifications else (self.now, nid))
            if primary != row.id:
                continue
            self._diff_scraper_fields(wi, title=f["title"], due_at=f["due_at"], due_source="parsed_from_text",
                                      instructions_md=f["instructions_md"], links=f["links"], kind=wi.kind,
                                      track_status=False)

    @staticmethod
    def _ref(row: NotificationRow) -> str | None:
        """The Nexus object a notification points at (an announcement or event), for de-duplication."""
        d = (row.payload or {}).get("data")
        if isinstance(d, dict):
            for k in ("announcementId", "eventId"):
                if d.get(k):
                    return f"{k}:{d[k]}"
        return None

    def _classify_new(self, row: NotificationRow) -> None:
        # The same announcement can arrive twice: as a notification and from the course page sweep.
        ref = self._ref(row)
        if ref:
            for other in self.s.notifications.values():
                if other.id != row.id and self._ref(other) == ref:
                    wid = next((w for (w, nid) in self.s.sources if nid == other.id), None)
                    if wid and wid in self.s.work_items:
                        self.s.sources.add((wid, row.id))
                        self.cs.sources_insert.add((wid, row.id))
                        wi = self.s.work_items[wid]
                        # prefer the fuller text when the new copy has it
                        f = self._notification_fields(row)
                        if wi.title_source != "user" and f["instructions_md"] and \
                                len(f["instructions_md"]) > len(wi.instructions_md or ""):
                            self._update(wi, instructions_md=f["instructions_md"])
                        self._event(wi, "linked", None, {"notification": row.nexus_notification_id})
                        self.stats.linked += 1
                        return
        c = self.classifier.classify(row, self.s)
        if c.linked_work_item_id and c.linked_work_item_id in self.s.work_items:
            wi = self.s.work_items[c.linked_work_item_id]
            self.s.sources.add((wi.id, row.id))
            self.cs.sources_insert.add((wi.id, row.id))
            if wi.origin == "assignments_tab":
                self._update(wi, origin="both")
            self._event(wi, "linked", None, {"notification": row.nexus_notification_id})
            self.stats.linked += 1
            return
        f = self._notification_fields(row)
        wi = WorkItem(
            id=new_id(), title=f["title"], origin="notification_only", kind=c.kind,
            course_id=c.course_id, due_at=f["due_at"], due_source="parsed_from_text" if f["due_at"] else None,
            instructions_md=f["instructions_md"], links=f["links"],
            classification=c.classification, confidence=c.confidence, classifier_reasons=c.reasons,
        )
        self._insert_item(wi)
        self.s.sources.add((wi.id, row.id))
        self.cs.sources_insert.add((wi.id, row.id))

    # ------------------------------------------------------------------ re-check Needs Review

    def reclassify_unresolved(self) -> None:
        """Give every item still in Needs Review another chance with today's evidence (new courses, learned
        aliases). Only `unresolved` items are touched — manual choices are sticky and auto-filed items stay."""
        for wi in list(self.s.work_items.values()):
            if wi.classification != "unresolved" or wi.course_id is not None or wi.origin != "notification_only":
                continue
            nids = [nid for (w, nid) in self.s.sources if w == wi.id and nid in self.s.notifications]
            if not nids:
                continue
            row = min((self.s.notifications[n] for n in nids), key=lambda r: (r.published_at or self.now, r.id))
            c = self.classifier.classify(row, self.s)
            if c.classification == "auto" and c.course_id:
                self._update(wi, course_id=c.course_id, classification="auto", confidence=c.confidence,
                             classifier_reasons=c.reasons)
                self._event(wi, "moved", None, c.course_id)
                self.stats.extra["reclassified"] = self.stats.extra.get("reclassified", 0) + 1
            elif c.reasons != wi.classifier_reasons:
                # keep the "Suggested:" chips current without logging an event
                self._update(wi, classifier_reasons=c.reasons, confidence=c.confidence)

    # ------------------------------------------------------------------ orchestration

    def run(self, fetched: Fetched) -> tuple[ChangeSet, SyncStats]:
        if fetched.courses is not None:
            self.sync_courses(fetched.courses, fetched.assignments)
        if fetched.assignments is not None:
            self.sync_assignments(fetched.assignments)
        if fetched.notifications is not None:
            self.sync_notifications(fetched.notifications)
        self.reclassify_unresolved()
        self.stats.extra["needs_review_total"] = sum(
            1 for w in self.s.work_items.values() if w.course_id is None and not w.is_hidden)
        return self.cs, self.stats


def run_pipeline(state: State, fetched: Fetched, now: datetime, nexus_base_url: str,
                 classifier: Classifier | None = None) -> tuple[ChangeSet, SyncStats]:
    return Pipeline(state, now, nexus_base_url, classifier).run(fetched)
