import copy
from datetime import timedelta

from conftest import by_title, course_named, fetched
from fixtures import ASSIGNMENTS, BASE, NOTIFICATIONS, NOW
from hypothesis import given, settings
from hypothesis import strategies as st

from eztracker.models import State
from eztracker.pipeline import actions
from eztracker.pipeline.merge import Fetched, run_pipeline


def test_second_sync_is_a_no_op(synced_state: State) -> None:
    cs, stats = run_pipeline(synced_state, fetched(), NOW, BASE)
    assert cs.is_empty_of_writes()
    assert stats.assignments_new == 0 and stats.notifications_new == 0 and stats.changed == 0


def test_first_sync_counts(synced_state: State) -> None:
    assert len(synced_state.courses) == 9
    assert len(synced_state.assignments) == 5
    assert len(synced_state.notifications) == 8
    # 5 assignment items + 8 notifications, of which 2 link into existing assignments
    assert len(synced_state.work_items) == 11


def test_submitted_on_nexus_syncs_my_status(synced_state: State) -> None:
    wi = by_title(synced_state, "Framework Drill")
    assert wi.my_status == "submitted" and wi.my_status_set_by == "default"


def test_failed_surface_does_not_wipe_other_data(synced_state: State) -> None:
    before = len(synced_state.work_items)
    cs, _ = run_pipeline(synced_state, Fetched(None, copy.deepcopy(ASSIGNMENTS), None), NOW, BASE)
    assert cs.is_empty_of_writes() and len(synced_state.work_items) == before


def test_due_change_logs_event_and_chip(synced_state: State) -> None:
    changed = copy.deepcopy(ASSIGNMENTS)
    changed[0].due_at = changed[0].due_at + timedelta(days=2)  # Zepto
    later = NOW + timedelta(hours=3)
    cs, stats = run_pipeline(synced_state, Fetched(None, changed, None), later, BASE)
    wi = by_title(synced_state, "Zepto Case Analysis")
    assert [e.event for e in cs.events] == ["due_changed"]
    assert wi.due_at == changed[0].due_at and wi.due_changed_at == later
    assert stats.changed == 1


def test_hidden_item_unhides_only_on_new_due(synced_state: State) -> None:
    wi = by_title(synced_state, "Rapido Pricing Memo")
    actions.patch_item(synced_state, wi.id, {"is_hidden": True}, "t")
    run_pipeline(synced_state, fetched(), NOW, BASE)
    assert wi.is_hidden
    changed = copy.deepcopy(ASSIGNMENTS)
    changed[2].due_at = changed[2].due_at + timedelta(days=4)
    run_pipeline(synced_state, Fetched(None, changed, None), NOW, BASE)
    assert not wi.is_hidden and wi.upstream_updated_at == NOW


def test_user_due_is_sticky_and_upstream_is_offered(synced_state: State) -> None:
    wi = by_title(synced_state, "Zepto Case Analysis")
    mine = NOW + timedelta(days=10)
    actions.patch_item(synced_state, wi.id, {"due_at": mine}, "t")
    changed = copy.deepcopy(ASSIGNMENTS)
    changed[0].due_at = NOW + timedelta(days=6)
    cs, _ = run_pipeline(synced_state, Fetched(None, changed, None), NOW, BASE)
    assert wi.due_at == mine and wi.due_source == "user"
    assert wi.upstream_due_at == changed[0].due_at
    assert [e.event for e in cs.events] == ["due_changed_upstream"]
    # accepting upstream
    actions.patch_item(synced_state, wi.id, {"due_at": None, "due_use_upstream": True}, "t2")
    assert wi.due_at == changed[0].due_at and wi.due_source == "nexus_field"


def test_notification_edit_refreshes_notification_only_item(synced_state: State) -> None:
    ns = copy.deepcopy(NOTIFICATIONS)
    ns[1].body_html = "<p>Submit your end term deck by 7th Oct, 11:59 PM.</p>"
    cs, _ = run_pipeline(synced_state, Fetched(None, None, ns), NOW, BASE)
    wi = by_title(synced_state, "Important: END TERM ASSIGNMENT")
    assert wi.due_at is not None and wi.due_at.day == 7
    assert "due_changed" in [e.event for e in cs.events]


# ------------------------------------------------------------------ sticky rules, property-style

mutations = st.fixed_dictionaries({
    "status": st.sampled_from(["Pending", "Submitted", "Graded", "Late"]),
    "due_shift_h": st.integers(-200, 200),
    "title_suffix": st.sampled_from(["", " (v2)", " — updated"]),
    "course": st.sampled_from([None, "Build Your Own Business (BYOB)", "Business Reader with Suprad",
                               "Unknown Course"]),
    "desc": st.sampled_from([None, "<p>new instructions</p>", "<p>Analyse again</p>"]),
})


@settings(max_examples=60, deadline=None)
@given(muts=st.lists(mutations, min_size=5, max_size=5), rounds=st.integers(1, 3))
def test_manual_fields_never_change_under_any_scraper_input(muts: list[dict], rounds: int) -> None:  # type: ignore[type-arg]
    s = State()
    run_pipeline(s, fetched(), NOW, BASE)
    reader = course_named(s, "Business Reader")
    pinned = []
    for a in ASSIGNMENTS:
        wi = next(w for w in s.work_items.values()
                  if w.assignment_raw_id and s.assignments[w.assignment_raw_id].nexus_assignment_id
                  == a.nexus_assignment_id)
        actions.move_item(s, wi.id, reader, "t")
        actions.set_status(s, wi.id, "in_progress", "t")
        actions.patch_item(s, wi.id, {"due_at": NOW + timedelta(days=30), "title": "Mine: " + a.title}, "t")
        pinned.append((wi.id, wi.course_id, wi.my_status, wi.due_at, wi.title, wi.classification))

    for _ in range(rounds):
        raws = copy.deepcopy(ASSIGNMENTS)
        for r, m in zip(raws, muts, strict=True):
            r.status_raw = m["status"]
            r.due_at = r.due_at + timedelta(hours=m["due_shift_h"]) if r.due_at else None
            r.title = r.title + m["title_suffix"]
            r.course_name_raw = m["course"]
            r.description_html = m["desc"]
        run_pipeline(s, Fetched(copy.deepcopy(fetched().courses), raws, copy.deepcopy(NOTIFICATIONS)), NOW, BASE)

    for wid, course, status, due, title, cls in pinned:
        wi = s.work_items[wid]
        assert (wi.course_id, wi.my_status, wi.due_at, wi.title, wi.classification) == \
            (course, status, due, title, cls)


def test_nexus_links_never_404() -> None:
    from eztracker.pipeline.merge import safe_nexus_url

    uid = "0c0ffee0-1111-4111-8111-000000000abc"
    assert safe_nexus_url(BASE, None, f"/student/lms/assignments/{uid}") == f"{BASE}/student/lms/assignments/{uid}"
    assert safe_nexus_url(BASE, f"{BASE}/student/lms/courses/{uid}", "/x") == f"{BASE}/student/lms/courses/{uid}"
    assert safe_nexus_url(BASE, None, "/student/lms/assignments/a-1") == f"{BASE}/student/lms/assignments"
    notif = f"{BASE}/student/lms/notifications"
    assert safe_nexus_url(BASE, "/student/lms/byob", "/student/lms/notifications") == notif
    assert safe_nexus_url(BASE, "https://evil.example/x", "/student/lms/notifications") == \
        f"{BASE}/student/lms/notifications"


def test_announcement_deep_link_is_kept() -> None:
    from eztracker.pipeline.merge import safe_nexus_url

    cid = "c1111111-1111-4111-8111-111111111111"
    url = "/student/community/5b7e2c9a-1111-4111-8111-000000000001?src=notification"
    assert safe_nexus_url(BASE, url, "/student/lms/notifications") == BASE + url
    assert safe_nexus_url(BASE, f"/student/lms/courses/{cid}", "/x") == f"{BASE}/student/lms/courses/{cid}"


def test_needs_review_is_rechecked_when_a_course_appears(synced_state: State) -> None:
    from eztracker.models import RawCourse

    wi = by_title(synced_state, "Start-up Leader Session")
    assert wi.course_id is None
    courses = [*fetched().courses, RawCourse("Start-up Leader Session", "c-sls", None, "Core",  # type: ignore[misc]
                                             "In Class", "Term 1", short_name="SLS")]
    cs, stats = run_pipeline(synced_state, Fetched(courses, copy.deepcopy(ASSIGNMENTS), copy.deepcopy(NOTIFICATIONS)),
                             NOW, BASE)
    assert wi.course_id == course_named(synced_state, "SLS") and wi.classification == "auto"
    assert stats.extra["reclassified"] == 1
    cs2, _ = run_pipeline(synced_state, fetched(), NOW, BASE)
    assert not cs2.events  # stable afterwards


def test_recheck_never_touches_manual_needs_review(synced_state: State) -> None:
    wi = by_title(synced_state, "Growth & GTM")
    actions.move_item(synced_state, wi.id, None, "t")  # user parked it in Needs Review on purpose
    from eztracker.models import RawCourse

    courses = [*fetched().courses, RawCourse("Growth and GTM Lab", "c-gtm", None, "Core", "In Class", "Term 1")]  # type: ignore[misc]
    run_pipeline(synced_state, Fetched(courses, None, None), NOW, BASE)
    assert wi.course_id is None and wi.classification == "manual"
