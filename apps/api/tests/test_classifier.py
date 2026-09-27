"""§7 required examples plus extra fixtures. Classification runs inside the full pipeline for realism."""

import copy

import pytest
from conftest import by_title, course_named
from fixtures import ASSIGNMENTS, BASE, COURSES, NOW, notif

from eztracker.models import RawCourse, State
from eztracker.pipeline.merge import Fetched, run_pipeline


def classify_one(title: str, snippet: str, category: str = "Announcement", body: str | None = None,
                 courses: list[RawCourse] | None = None, with_assignments: bool = True) -> tuple[State, str | None]:
    s = State()
    n = notif("x-1", title, snippet, category, body=body)
    run_pipeline(s, Fetched(copy.deepcopy(courses or COURSES),
                            copy.deepcopy(ASSIGNMENTS) if with_assignments else [], [n]), NOW, BASE)
    wi = next(w for w in s.work_items.values() if w.origin in ("notification_only", "both")
              and (w.origin == "notification_only" or any(src[0] == w.id for src in s.sources)))
    short = s.courses[wi.course_id].short_name if wi.course_id else None
    return s, short


# ---------------------------------------------------------------- the seven required examples

def test_lenskart_workbook_goes_to_dddm(synced_state: State) -> None:
    wi = by_title(synced_state, "Session 7 Lenskart Workbook")
    assert wi.course_id == course_named(synced_state, "DDDM")
    assert wi.classification == "auto"
    assert wi.origin == "both"  # linked to the My Work assignment rather than duplicated


def test_lenskart_without_assignment_is_suggested_not_filed() -> None:
    s, short = classify_one("New announcement", "Session 7 Lenskart Workbook", with_assignments=False)
    wi = next(iter(s.work_items.values()))
    assert short is None and wi.classification == "unresolved"
    assert wi.classifier_reasons == []  # no DDDM assignments seen → no lenskart alias yet


def test_end_term_crafting_marketing(synced_state: State) -> None:
    wi = by_title(synced_state, "Important: END TERM ASSIGNMENT")
    assert wi.course_id == course_named(synced_state, "CMS")
    assert wi.classification == "auto"
    assert wi.kind == "announcement_task"
    assert wi.due_at is not None and wi.due_source == "parsed_from_text"


def test_business_reader_assessment(synced_state: State) -> None:
    wi = by_title(synced_state, "Important: Assessment Details for Business Reader")
    assert wi.course_id == course_named(synced_state, "Business Reader")
    assert wi.classification == "auto"
    assert wi.kind != "info"


def test_startup_leader_needs_review(synced_state: State) -> None:
    wi = by_title(synced_state, "Start-up Leader Session")
    assert wi.course_id is None and wi.classification == "unresolved"


def test_startup_leader_suggested_when_course_exists() -> None:
    # §7 allows either outcome; two distinctive alias hits (0.50) make it the top suggestion, not auto-filed.
    courses = [*COURSES, RawCourse("Start-up Leader Series", "c-sls", None, "Soft Skills", "In Class", "Term 1")]
    s, short = classify_one("New announcement", "Start-up Leader Session: Final Groups", courses=courses)
    wi = next(w for w in s.work_items.values() if w.origin == "notification_only")
    assert short is None
    assert wi.classifier_reasons[0]["course"] == "SULS"


def test_clubs_is_info_and_unfiled(synced_state: State) -> None:
    wi = by_title(synced_state, "CLUBS ARE FINALLY HERE")
    assert wi.kind == "info" and wi.course_id is None


def test_byob_leaderboard_is_byob_info(synced_state: State) -> None:
    wi = by_title(synced_state, "Your BYOB leaderboard")
    assert wi.course_id == course_named(synced_state, "BYOB")
    assert wi.kind == "info"


def test_growth_gtm_panel_is_ambiguous(synced_state: State) -> None:
    wi = by_title(synced_state, "Growth & GTM")
    assert wi.course_id is None and wi.classification == "unresolved"


# ---------------------------------------------------------------- 20 more fixtures

@pytest.mark.parametrize("title,snippet,category,body,expected_course,expected_task", [
    ("New announcement", "DDDM quiz on Friday", "Announcement", None, "DDDM", True),
    ("New announcement", "Rapido case: pre-read for Vinay's class", "Announcement", None, None, False),
    ("New announcement", "Blinkit workbook uploaded", "Announcement", None, None, True),  # alias alone < 0.70
    ("New assignment", "Rapido Pricing Memo", "Assignment", None, "DDDM", True),           # links to assignment
    ("New announcement", "Business Frameworks: Porter's Five Forces drill", "Announcement", None,
     "Business Framewo…", True),  # links to the drill assignment
    ("New announcement", "Reminder: Framework Drill Porter's Five Forces due tonight", "Announcement", None,
     "Business Framewo…", True),
    ("New announcement", "Pranjal's frameworks session moved to Room 204", "Announcement", None,
     None, False),
    ("New announcement", "Business Reader: book list for Term 1", "Announcement", None, "Business Reader", False),
    ("New announcement", "Suprad's reader circle — submit reflections by 2nd Oct", "Announcement", None,
     None, True),
    ("New announcement", "BYOB Milestone 2 submission guidelines", "Announcement", None, "BYOB", True),
    ("New announcement", "Build Your Own Business: demo day schedule", "Announcement", None, "BYOB", False),
    ("New announcement", "AI Workshops: bring your laptop", "Announcement", None, "AI Workshops", False),
    ("New announcement", "Career Readiness: CV upload deadline 1 Oct", "Announcement", None,
     "Career Readiness", True),
    ("New announcement", "Crafting Marketing Strategies – Session 4 slides", "Announcement", None, "CMS", False),
    ("New announcement", "Siddarth Menon: guest lecture on positioning", "Announcement", None, None, False),
    ("New announcement", "Library timings extended", "General", None, None, False),
    ("New announcement", "Placement panel this Thursday", "General", None, None, False),
    ("New announcement", "Hostel maintenance notice", "General", None, None, False),
    ("New announcement", "Opt-in form for Wednesday offsite", "General", None, None, True),
    ("New announcement", "Orientation Week photos are up", "General", None, "Orientation Week", False),
])
def test_more_fixtures(title: str, snippet: str, category: str, body: str | None,
                       expected_course: str | None, expected_task: bool) -> None:
    s, short = classify_one(title, snippet, category, body)
    assert short == expected_course
    wi = next(w for w in s.work_items.values()
              if w.origin == "notification_only" or any(src[0] == w.id for src in s.sources))
    assert (wi.kind != "info") == expected_task, wi.kind


@pytest.mark.parametrize("snippet,top", [
    ("Rapido case: pre-read for Vinay's class", "DDDM"),
    ("Pranjal's frameworks session moved to Room 204", "Business Framewo…"),
    ("Suprad's reader circle — submit reflections by 2nd Oct", "Business Reader"),
])
def test_needs_review_items_carry_the_right_suggestion(snippet: str, top: str) -> None:
    s, _ = classify_one("New announcement", snippet)
    wi = next(w for w in s.work_items.values() if w.origin == "notification_only")
    assert wi.classifier_reasons[0]["course"] == top


def test_needs_review_keeps_top_two_suggestions() -> None:
    s, short = classify_one("New announcement", "Vinay and Suprad joint session notes")
    wi = next(w for w in s.work_items.values() if w.origin == "notification_only")
    assert short is None
    assert {r["course"] for r in wi.classifier_reasons} == {"DDDM", "Business Reader"}
