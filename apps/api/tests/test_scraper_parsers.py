"""Pure parser tests for both strategies + discovery redaction. No browser, no network."""

from datetime import UTC, datetime

from eztracker.pipeline.dates import IST
from eztracker.scraper.adapters.base import SchemaMismatch, best_list
from eztracker.scraper.adapters.dom_strategy import (
    parse_assignment_block,
    parse_course_block,
    parse_notification_block,
)
from eztracker.scraper.adapters.json_strategy import map_assignment, map_course, map_notification
from eztracker.scraper.discovery import normalize_endpoint, redact
from eztracker.scraper.session import CapturedResponse  # noqa: F401 — import smoke

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
BASE = "https://students.mesaschool.co.in"
UID = "3f2b8c1e-9a4d-4e21-8b3c-1d2e3f4a5b6c"

ASSIGNMENTS_JSON = {"success": True, "data": {"items": [
    {"_id": UID, "title": "Session 7 Lenskart Workbook", "course": {"name": "Data Driven Decision Making"},
     "dueDate": "2026-09-30T18:29:00.000Z", "status": "Pending", "assignmentType": "Individual",
     "attachments": [{"fileName": "brief.pdf", "fileUrl": "https://cdn.example/brief.pdf"}]},
    {"_id": "a2", "title": "Rapido Pricing Memo", "course": {"name": "DDDM"}, "dueDate": None, "status": "Submitted"},
], "page": 1}, "user": {"email": "someone@mesaschool.co", "firstName": "A"}}

NOTIFS_JSON = {"notifications": [
    {"id": "n1", "title": "New announcement", "message": "Session 7 Lenskart Workbook", "type": "Announcement",
     "createdAt": "2026-09-26T10:00:00Z", "isRead": False},
    {"id": "n2", "title": "New assignment", "message": "<p>Zepto <b>case</b></p>", "type": "Assignment",
     "createdAt": "2026-09-25T10:00:00Z", "isRead": True, "redirectUrl": f"/student/lms/assignments/{UID}"},
]}

COURSES_JSON = [{"id": "c1", "name": "Business Reader with Suprad", "instructor": {"name": "Suprad"},
                 "category": "Soft Skills", "mode": "In Class", "term": "Term 1"},
                {"id": "c2", "name": "Career Readiness", "faculty": ["X", "Y"], "category": "Soft Skills",
                 "deliveryMode": "Hybrid", "term": {"name": "Term 1"}}]


def test_best_list_finds_assignments_among_noise() -> None:
    items = best_list([{"menu": [{"label": "Home"}]}, ASSIGNMENTS_JSON], "assignments")
    assert len(items) == 2
    a = map_assignment(items[0], BASE, NOW)
    assert a and a.nexus_assignment_id == UID and a.course_name_raw == "Data Driven Decision Making"
    assert a.due_at == datetime(2026, 9, 30, 18, 29, tzinfo=UTC)
    assert a.attachments == [{"name": "brief.pdf", "url": "https://cdn.example/brief.pdf"}]
    assert a.url == f"{BASE}/student/lms/assignments/{UID}"


def test_best_list_raises_on_wrong_shape() -> None:
    try:
        best_list([{"menu": [{"label": "Home"}]}], "assignments")
        raise AssertionError("expected SchemaMismatch")
    except SchemaMismatch:
        pass


def test_notifications_map() -> None:
    items = best_list([NOTIFS_JSON], "notifications")
    n1, n2 = (map_notification(o, NOW) for o in items)
    assert n1 and n1.is_unread_on_nexus is True and n1.category_raw == "Announcement"
    assert n2 and n2.body_html == "<p>Zepto <b>case</b></p>" and n2.snippet == "Zepto case"
    assert n2.link_url and UID in n2.link_url


def test_notification_without_id_gets_stable_hash() -> None:
    o = {"title": "CLUBS ARE FINALLY HERE!", "message": "Sign up", "createdAt": "Yesterday"}
    a, b = map_notification(o, NOW), map_notification(dict(o), NOW)
    assert a and b and a.nexus_notification_id == b.nexus_notification_id
    assert a.nexus_notification_id.startswith("h_")
    assert a.published_at and a.published_at.astimezone(IST).day == 26


def test_courses_map() -> None:
    items = best_list([COURSES_JSON], "courses")
    c1, c2 = (map_course(o) for o in items)
    assert c1 and c1.instructor == "Suprad" and c1.mode == "In Class"
    assert c2 and c2.instructor == "X, Y" and c2.term == "Term 1" and c2.mode == "Hybrid"


def test_dom_assignment_card() -> None:
    text = "30\nSEP\nSession 7 Lenskart Workbook\nIndividual\nData Driven Decision Making\nDue 30 Sep\nPending"
    a = parse_assignment_block(f"/student/lms/assignments/{UID}", text, BASE, NOW)
    assert a and a.title == "Session 7 Lenskart Workbook" and a.type_raw == "Individual"
    assert a.course_name_raw == "Data Driven Decision Making" and a.status_raw == "Pending"
    assert a.due_at and a.due_at.astimezone(IST).strftime("%d %b %H:%M") == "30 Sep 23:59"


def test_dom_course_card() -> None:
    c = parse_course_block("Business Reader with Suprad\nSuprad\nSoft Skills\nIn Class", "Term 1")
    assert c and c.name == "Business Reader with Suprad" and c.category == "Soft Skills" and c.mode == "In Class"


def test_dom_notification_item() -> None:
    n = parse_notification_block("New announcement\nAnnouncement\nImportant: END TERM ASSIGNMENT – Crafting "
                                 "Marketing Strategy\nYesterday", None, True, NOW)
    assert n and n.title == "New announcement" and n.category_raw == "Announcement"
    assert n.snippet and n.snippet.startswith("Important: END TERM")
    assert n.published_at and n.published_at.astimezone(IST).day == 26


def test_redaction() -> None:
    r = redact(ASSIGNMENTS_JSON)
    assert r["user"]["email"] == "[redacted]" and r["user"]["firstName"] == "[redacted]"
    assert redact("call +91 98765 43210 or mail a.b@x.co") == "call [phone] or mail [email]"
    assert redact({"accessToken": "eyJabc"}) == {"accessToken": "[redacted]"}
    assert normalize_endpoint(f"https://api.x/v1/assignments/{UID}?x=1") == "https://api.x/v1/assignments/{uuid}"


# ------------------------------------------------ real Nexus shapes (docs/nexus_api_map.md; values synthetic)

C_DDDM = "f2395447-0000-4000-8000-000000000001"
C_CMS = "f2395447-0000-4000-8000-000000000002"
A_ZEPTO = "a0000000-0000-4000-8000-000000000001"
TERM1 = "17a4f404-0000-4000-8000-000000000009"

NEXUS_COURSES = {"data": {"courses": [
    {"id": C_DDDM, "title": "Data Driven Decision Making with Prof. Vinay Sharma", "shortName": "DDDM",
     "instructorName": "Vinay Sharma", "courseType": "Core", "classType": "In Class", "termId": TERM1,
     "coverImageUrl": "https://x/y.jpg", "description": None, "code": None, "sequence": None, "startDate": None,
     "endDate": None, "visible": True, "createdAt": "2026-07-01T00:00:00Z", "updatedAt": "2026-07-01T00:00:00Z"},
    {"id": C_CMS, "title": "Crafting Marketing Strategies with Prof. Siddarth Menon", "shortName": "CMS",
     "instructorName": "Siddarth Menon", "courseType": "Core", "classType": "In Class", "termId": TERM1,
     "coverImageUrl": "https://x/z.jpg", "description": None, "code": None, "sequence": None, "startDate": None,
     "endDate": None, "visible": True, "createdAt": "2026-07-01T00:00:00Z", "updatedAt": "2026-07-01T00:00:00Z"},
]}}

NEXUS_MY = {"data": {"assignments": [
    {"id": A_ZEPTO, "title": "Zepto Case Analysis", "courseId": C_DDDM,
     "courseTitle": "Data Driven Decision Making with Prof. Vinay Sharma", "dueAt": "2026-09-30T18:29:00.000Z",
     "cutoffDate": None, "allowLate": False, "description": "<p>Dark-store economics.</p>",
     "instructions": "<ul><li>Max 3 pages</li></ul>", "isGroup": True, "mySubmissionStatus": None,
     "status": "published", "submissionType": "file", "materials": [
         {"id": "m1", "title": "Case PDF", "kind": "file", "url": "https://storage.example/case.pdf",
          "fileName": "case.pdf", "fileType": "application/pdf", "fileSizeBytes": 1000, "position": 0}]},
    {"id": "a0000000-0000-4000-8000-000000000002", "title": "Porter drill", "courseId": None, "courseTitle": None,
     "dueAt": None, "description": None, "instructions": None, "isGroup": False, "mySubmissionStatus": "submitted",
     "status": "published", "materials": []},
]}}

NEXUS_NOTIFS = {"data": {"hasMore": False, "unread": 2, "items": [
    {"id": "n0000000-0000-4000-8000-000000000001", "type": "announcement", "title": "New announcement",
     "body": "<p>Growth &amp; GTM: 'What Is' Panel</p>", "createdAt": "2026-09-26T10:00:00Z", "isRead": False,
     "data": {"courseId": C_CMS, "announcementId": "an-1"}},
    {"id": "n0000000-0000-4000-8000-000000000002", "type": "assignment_new", "title": "New assignment",
     "body": "Zepto Case Analysis", "createdAt": "2026-09-25T10:00:00Z", "isRead": True,
     "data": {"courseId": C_DDDM, "assignmentId": A_ZEPTO}},
    {"id": "n0000000-0000-4000-8000-000000000003", "type": "system", "title": "Your BYOB leaderboard has been updated",
     "body": "See where you stand", "createdAt": "2026-09-24T10:00:00Z", "isRead": True,
     "data": {"url": "/student/lms/byob", "source": "byob"}},
]}}


def test_nexus_courses_shape() -> None:
    from eztracker.scraper.adapters.json_strategy import map_course as mc

    items = best_list([NEXUS_COURSES], "courses", threshold=1.0)
    c = mc(items[0], "Term 1")
    assert c and c.nexus_course_id == C_DDDM and c.short_name == "DDDM" and c.instructor == "Vinay Sharma"
    assert (c.category, c.mode, c.term) == ("Core", "In Class", "Term 1")


def test_nexus_my_assignments_shape() -> None:
    items = best_list([{"data": {"forms": []}}, NEXUS_MY], "assignments")
    a, b = (map_assignment(o, BASE, NOW) for o in items)
    assert a and a.status_raw == "Pending" and a.type_raw == "Group"
    assert a.due_at == datetime(2026, 9, 30, 18, 29, tzinfo=UTC)
    assert a.description_html and "Max 3 pages" in a.description_html and "Dark-store" in a.description_html
    assert a.attachments == [{"name": "Case PDF", "url": "https://storage.example/case.pdf"}]
    assert b and b.status_raw == "Submitted" and b.course_name_raw is None


def test_nexus_notifications_shape() -> None:
    items = best_list([NEXUS_NOTIFS], "notifications")
    ann, new_a, sysn = (map_notification(o, NOW) for o in items)
    assert ann and ann.category_raw == "Announcement" and ann.link_url == "/student/community/an-1?src=notification"
    assert ann.snippet == "Growth & GTM: 'What Is' Panel"
    assert ann.is_unread_on_nexus is True
    assert new_a and new_a.category_raw == "Assignment" and A_ZEPTO in (new_a.link_url or "")
    assert sysn and sysn.category_raw == "General" and sysn.link_url == "/student/lms/byob"


def test_announcement_bodies_tolerant() -> None:
    from eztracker.scraper.adapters.json_strategy import announcement_bodies

    got = announcement_bodies([{"data": {"announcements": [
        {"id": "an-1", "title": "Panel", "content": "<p>Full text, submit by 5 Oct</p>", "createdAt": "x"}]}}])
    assert got == {"an-1": "<h3>Panel</h3><p>Full text, submit by 5 Oct</p>"}


def test_nexus_course_ids_make_classification_exact() -> None:
    """With real Nexus ids, an announcement names its course → auto-filed even with no text signal."""
    import copy as _copy

    from eztracker.models import State
    from eztracker.pipeline.merge import Fetched, run_pipeline

    now = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    courses = [mc for mc in (map_course(o, "Term 1") for o in NEXUS_COURSES["data"]["courses"]) if mc]
    assigns = [x for x in (map_assignment(o, BASE, now) for o in NEXUS_MY["data"]["assignments"]) if x]
    notes = [x for x in (map_notification(o, now) for o in NEXUS_NOTIFS["data"]["items"]) if x]
    s = State()
    run_pipeline(s, Fetched(courses, assigns, notes), now, BASE)
    by = {w.title: w for w in s.work_items.values()}
    cms = next(c.id for c in s.courses.values() if c.nexus_course_id == C_CMS)
    dddm = next(c.id for c in s.courses.values() if c.nexus_course_id == C_DDDM)
    assert by["Growth & GTM: 'What Is' Panel"].course_id == cms  # was Needs Review on text alone
    assert by["Growth & GTM: 'What Is' Panel"].classification == "auto"
    assert by["Zepto Case Analysis"].course_id == dddm and by["Zepto Case Analysis"].origin == "both"
    assert s.courses[dddm].short_name == "DDDM"
    cs, _ = run_pipeline(s, Fetched(_copy.deepcopy(courses), _copy.deepcopy(assigns), _copy.deepcopy(notes)), now, BASE)
    assert cs.is_empty_of_writes()


def test_links_mirror_nexus_click_handler() -> None:
    """The exact destinations Nexus's own notification list navigates to (from its front-end code)."""
    from eztracker.scraper.adapters.json_strategy import _notification_link as link

    community = "/student/community/an-9?src=notification"
    assert link("announcement", {"courseId": C_CMS, "announcementId": "an-9"}) == community
    assert link("reply", {"announcementId": "an-9"}) == "/student/community/an-9?src=notification"
    assert link("announcement", {"courseId": C_CMS}) == f"/student/lms/courses/{C_CMS}"
    assert link("assignment_due", {"assignmentId": A_ZEPTO}) == f"/student/lms/assignments/{A_ZEPTO}"
    assert link("graded", {"assignmentId": A_ZEPTO}) == f"/student/lms/assignments/{A_ZEPTO}"
    assert link("system", {"subtype": "calendar_event", "url": "/x"}) == "/student/lms/calendar"
    assert link("system", {"url": "/student/lms/attendance"}) == "/student/lms/attendance"


def test_one_word_new_assignment_links_by_id() -> None:
    from eztracker.models import State
    from eztracker.pipeline.merge import Fetched, run_pipeline

    now = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    courses = [x for x in (map_course(o, "Term 1") for o in NEXUS_COURSES["data"]["courses"]) if x]
    assigns = [x for x in (map_assignment(o, BASE, now) for o in NEXUS_MY["data"]["assignments"]) if x]
    n = map_notification({"id": "n-x", "type": "assignment_new", "title": "New assignment", "body": "Zepto",
                          "createdAt": "2026-09-25T10:00:00Z", "isRead": False,
                          "data": {"courseId": C_DDDM, "assignmentId": A_ZEPTO}}, now)
    s = State()
    run_pipeline(s, Fetched(courses, assigns, [n] if n else []), now, BASE)
    zepto = next(w for w in s.work_items.values() if w.title == "Zepto Case Analysis")
    assert zepto.origin == "both" and len(s.work_items) == 2  # linked, not a duplicate


def test_courses_hidden_on_nexus_start_archived() -> None:
    from eztracker.models import State
    from eztracker.pipeline.merge import Fetched, run_pipeline

    hidden = {**NEXUS_COURSES["data"]["courses"][0], "id": "hidden-1", "title": "Workshops", "visible": False}
    cs = [x for x in (map_course(o, "Term 1") for o in [*NEXUS_COURSES["data"]["courses"], hidden]) if x]
    s = State()
    run_pipeline(s, Fetched(cs, [], []), datetime(2026, 9, 27, tzinfo=UTC), BASE)
    by = {c.name: c for c in s.courses.values()}
    assert by["Workshops"].is_archived and not by["Data Driven Decision Making with Prof. Vinay Sharma"].is_archived


def test_a_differently_shaped_page_is_not_dropped() -> None:
    """Regression: the Pre-Term course (no instructor) was discarded next to the richer Term 1 list."""
    from eztracker.scraper.adapters.base import lists_per_body

    pre = {"data": {"courses": [{"id": "pre-1", "title": "Orientation Week", "shortName": "OW", "instructorName": None,
                                 "courseType": "Soft Skills", "classType": "In Class", "termId": "t0",
                                 "description": "Welcome"}]}}
    both = [NEXUS_COURSES, pre]
    assert {o["id"] for o in lists_per_body(both, "courses", threshold=1.0)} == {C_DDDM, C_CMS, "pre-1"}
    assert "pre-1" not in {o["id"] for o in best_list(both, "courses", threshold=1.0)}  # the old behaviour
