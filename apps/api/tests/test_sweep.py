"""Completeness sweep against a fake Nexus that serves canned API responses per page (shapes from the map)."""

import copy
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from eztracker.models import State
from eztracker.pipeline.merge import Fetched, run_pipeline
from eztracker.scraper.adapters.json_strategy import map_assignment, map_course, map_notification
from eztracker.scraper.session import CapturedResponse
from eztracker.scraper.sweep import run_sweep

BASE = "https://students.mesaschool.co.in"
API = "https://api-students.mesaschool.co.in/api/v1"
NOW = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
C1 = "c1111111-1111-4111-8111-111111111111"
A1 = "a1111111-1111-4111-8111-111111111111"
A2 = "a2222222-2222-4222-8222-222222222222"

COURSE = {"id": C1, "title": "Crafting Marketing Strategies with Prof. Siddarth Menon", "shortName": "CMS",
          "instructorName": "Siddarth Menon", "courseType": "Core", "classType": "In Class", "termId": "t1"}
MY = {"id": A1, "title": "Positioning memo", "courseId": C1, "courseTitle": COURSE["title"],
      "dueAt": "2026-10-01T18:29:00Z", "description": None, "instructions": None, "isGroup": False,
      "mySubmissionStatus": None, "status": "published", "materials": []}
NOTIF = {"id": "n1", "type": "announcement", "title": "New announcement", "body": "Important: END TERM…",
         "createdAt": "2026-09-26T10:00:00Z", "isRead": False, "data": {"courseId": C1, "announcementId": "an-1"}}

PAGES: dict[str, list[tuple[str, Any]]] = {
    f"/student/lms/courses/{C1}": [
        (f"{API}/announcements?courseId={C1}", {"data": {"announcements": [
            {"id": "an-1", "title": "END TERM ASSIGNMENT", "body": "<p>Submit the deck by 5th Oct, 11:59 PM.</p>",
             "createdAt": "2026-09-26T10:00:00Z"},
            {"id": "an-2", "title": "Reading for week 6", "body": "<p>Read chapter 4 before class.</p>",
             "createdAt": "2026-09-20T10:00:00Z"}]}}),
        (f"{API}/assignments?courseId={C1}&status=published", {"data": {"assignments": [
            {**MY},
            {"id": A2, "title": "Peer review of positioning memos", "courseId": C1, "dueAt": "2026-10-03T18:29:00Z",
             "description": "<p>Review two memos.</p>", "status": "published", "isGroup": False}]}}),
        (f"{API}/curriculum/topics?courseId={C1}", {"data": {"topics": [{"id": "x", "title": "Week 1"}]}}),
    ],
    "/student/lms/assignments": [
        (f"{API}/forms/mine", {"data": {"forms": [{"id": "f1", "title": "Elective preference form",
                                                  "closesAt": "2026-09-29T18:29:00Z", "submitted": False}]}}),
    ],
    "/student/lms/calendar": [
        (f"{API}/calendar/events?from=x", {"data": {"events": [
            {"id": "e1", "title": "DDDM mid-term exam", "startAt": "2026-10-08T04:30:00Z", "courseId": C1},
            {"id": "e2", "title": "Session 9: Pricing", "startAt": "2026-10-02T04:30:00Z", "courseId": C1}]}}),
        (f"{API}/mrs/assessments", {"data": {"visible": True, "maxMarks": 100, "assessments": [
            {"slug": "baseline", "title": "Baseline", "blurb": "Where you start", "status": "open", "tint": "green",
             "mrsScore": None, "totalMarks": 100, "partsSubmitted": 1},
            {"slug": "midpoint", "title": "Midpoint", "blurb": "Halfway", "status": "locked", "tint": "gray",
             "mrsScore": None, "totalMarks": 100, "partsSubmitted": None}]}}),
        (f"{API}/coach/unknown-list", {"data": {"things": [{"id": "z", "title": "Mystery"}]}}),
    ],
}


class FakePage:
    def get_by_role(self, *a: Any, **k: Any) -> "FakePage":
        return self

    @property
    def first(self) -> "FakePage":
        return self

    async def count(self) -> int:
        return 0

    async def wait_for_load_state(self, *a: Any) -> None:
        return None


class FakeSession:
    base_url = BASE

    def __init__(self) -> None:
        self.captured: list[CapturedResponse] = []
        self.page = FakePage()
        self._bucket: list[CapturedResponse] | None = None
        self.visited: list[str] = []

    @asynccontextmanager
    async def capture(self):  # type: ignore[no-untyped-def]
        self._bucket = []
        yield self._bucket
        self.captured.extend(self._bucket)
        self._bucket = None

    async def goto(self, path: str, wait: str = "networkidle") -> None:
        self.visited.append(path)
        for url, body in PAGES.get(path, []):
            assert self._bucket is not None
            self._bucket.append(CapturedResponse(url, "GET", 200, {}, copy.deepcopy(body)))

    async def polite_pause(self) -> None:
        return None


async def _run() -> tuple[FakeSession, Any, list[Any], list[Any], list[Any]]:
    courses = [c for c in [map_course(COURSE, "Term 1")] if c]
    assigns = [a for a in [map_assignment(MY, BASE, NOW)] if a]
    notes = [n for n in [map_notification(NOTIF, NOW)] if n]
    sess = FakeSession()
    sw = await run_sweep(sess, courses, assigns, notes)  # type: ignore[arg-type]
    return sess, sw, courses, assigns, notes


async def test_sweep_visits_every_course_and_fills_announcement_text() -> None:
    sess, sw, _, _, notes = await _run()
    assert f"/student/lms/courses/{C1}" in sess.visited
    assert notes[0].body_html and "5th Oct" in notes[0].body_html  # snippet replaced by full text


async def test_sweep_finds_what_the_main_surfaces_miss() -> None:
    _, sw, _, _, _ = await _run()
    ids = {a.nexus_assignment_id for a in sw.assignments}
    assert A2 in ids and A1 not in ids                     # course-only assignment added, no duplicate
    assert "form:f1" in ids                                # forms tab
    extra = {n.nexus_notification_id for n in sw.notifications}
    assert "ann:an-2" in extra and "ann:an-1" not in extra # orphan announcement only
    assert "evt:e1" in extra and "evt:e2" not in extra     # exam kept, ordinary class session skipped
    assert sw.coverage["orphan_announcements"] == 1 and sw.coverage["forms"] == 1


async def test_coverage_audit_flags_unread_endpoints() -> None:
    _, sw, _, _, _ = await _run()
    assert "/api/v1/coach/unknown-list" not in sw.coverage["unread_endpoints"]  # coach/* deliberately ignored
    assert "/api/v1/mrs/assessments" not in sw.coverage["unread_endpoints"]  # now read
    assert "/api/v1/curriculum/topics" not in sw.coverage["unread_endpoints"]  # deliberately ignored
    assert "/api/v1/calendar/events" not in sw.coverage["unread_endpoints"]    # read by the calendar pass
    assert sw.coverage["mrs_assessments"] == 2


async def test_sweep_output_flows_through_pipeline_without_duplicates() -> None:
    _, sw, courses, assigns, notes = await _run()
    s = State()
    fetched = Fetched(courses, assigns + sw.assignments, notes + sw.notifications)
    run_pipeline(s, copy.deepcopy(fetched), NOW, BASE)
    titles = sorted(w.title for w in s.work_items.values())
    assert "Peer review of positioning memos" in titles and "Elective preference form" in titles
    assert "DDDM mid-term exam" in titles and "Reading for week 6" in titles
    exam = next(w for w in s.work_items.values() if w.title == "DDDM mid-term exam")
    assert exam.due_at == datetime(2026, 10, 8, 4, 30, tzinfo=UTC) and exam.kind == "exam"
    form = next(w for w in s.work_items.values() if w.title == "Elective preference form")
    assert form.kind == "form" and form.course_id is None
    cms = next(c.id for c in s.courses.values() if c.nexus_course_id == C1)
    assert all(w.course_id == cms for w in s.work_items.values() if w.title in
               {"Peer review of positioning memos", "Reading for week 6", "DDDM mid-term exam"})
    # the announcement arriving later from the other channel links instead of duplicating
    later = copy.deepcopy(notes + sw.notifications)
    dup = copy.deepcopy(next(n for n in sw.notifications if n.nexus_notification_id == "ann:an-2"))
    dup.nexus_notification_id = "n-late"
    dup.payload = {"type": "announcement", "data": {"courseId": C1, "announcementId": "an-2"}}
    cs, _ = run_pipeline(s, Fetched(copy.deepcopy(courses), copy.deepcopy(assigns + sw.assignments), later + [dup]),
                         NOW, BASE)
    assert not cs.work_items_insert and len(cs.sources_insert) == 1
    cs2, _ = run_pipeline(s, copy.deepcopy(Fetched(courses, assigns + sw.assignments, later + [dup])), NOW, BASE)
    assert cs2.is_empty_of_writes()


async def test_unknown_list_is_warned_with_key_shape_only() -> None:
    extra = (f"{API}/brand-new/things", {"data": {"things": [{"id": "z", "secret": "v"}]}})
    PAGES["/student/lms/calendar"].append(extra)
    try:
        _, sw, _, _, _ = await _run()
    finally:
        PAGES["/student/lms/calendar"].pop()
    assert "/api/v1/brand-new/things" in sw.coverage["unread_endpoints"]
    shape = sw.coverage["unread_shapes"]["/api/v1/brand-new/things"]
    assert shape == {"data": {"things": [{"id": "str", "secret": "str"}]}}  # names and types, never values
    assert any(e["surface"] == "coverage" for e in sw.errors)


async def test_mrs_assessments_become_items_with_their_own_page() -> None:
    _, sw, courses, assigns, notes = await _run()
    mrs = {a.nexus_assignment_id: a for a in sw.assignments if a.nexus_assignment_id.startswith("mrs:")}
    assert set(mrs) == {"mrs:baseline", "mrs:midpoint"}
    assert mrs["mrs:baseline"].url == f"{BASE}/student/lms/mesa-readiness-score/baseline"
    assert mrs["mrs:midpoint"].status_raw == "Locked"
    assert [c.short_name for c in sw.courses] == ["MRS"]
    s = State()
    run_pipeline(s, Fetched(courses + sw.courses, assigns + sw.assignments, notes + sw.notifications), NOW, BASE)
    base = next(w for w in s.work_items.values() if w.title == "Baseline")
    assert base.course_id and s.courses[base.course_id].short_name == "MRS"
    assert base.links[0]["url"] == f"{BASE}/student/lms/mesa-readiness-score/baseline"
