import pytest
from conftest import by_title, course_named, fetched
from fixtures import BASE, NOW

from eztracker.models import State
from eztracker.pipeline import actions
from eztracker.pipeline.merge import run_pipeline


def _events(cs, token):  # type: ignore[no-untyped-def]
    return [{"event": e.event, "work_item_id": e.work_item_id, "from_value": e.from_value,
             "to_value": e.to_value} for e in reversed(cs.events) if e.undo_token == token]


def test_move_sets_manual_survives_sync_and_learns(synced_state: State) -> None:
    s = synced_state
    wi = by_title(s, "Growth & GTM")
    cms = course_named(s, "CMS")
    cs = actions.move_item(s, wi.id, cms, "tok")
    assert wi.course_id == cms and wi.classification == "manual"
    learned = [a.alias for a in cs.aliases_insert.values()]
    assert "growth" in learned and "gtm" in learned and "panel" not in learned  # generic never learned
    assert all(a.source == "learned" and a.weight == 0.5 for a in cs.aliases_insert.values())
    run_pipeline(s, fetched(), NOW, BASE)
    assert wi.course_id == cms and wi.classification == "manual"


def test_move_away_decrements_then_deletes_learned_alias(synced_state: State) -> None:
    s = synced_state
    wi = by_title(s, "Growth & GTM")
    cms, byob = course_named(s, "CMS"), course_named(s, "BYOB")
    actions.move_item(s, wi.id, cms, "t1")
    growth = next(a for a in s.aliases_for(cms) if a.alias == "growth")
    actions.move_item(s, wi.id, byob, "t2")
    assert growth.weight == 0.25
    actions.move_item(s, wi.id, cms, "t3")
    actions.move_item(s, wi.id, byob, "t4")
    assert growth.id not in s.aliases


def test_undo_move_restores_course_and_forgets_aliases(synced_state: State) -> None:
    s = synced_state
    wi = by_title(s, "Growth & GTM")
    cs = actions.move_item(s, wi.id, course_named(s, "CMS"), "tok")
    learned_ids = list(cs.aliases_insert)
    actions.undo(s, _events(cs, "tok"), "tok")
    assert wi.course_id is None and wi.classification == "unresolved"
    assert not any(a in s.aliases for a in learned_ids)


def test_move_back_to_needs_review_is_sticky(synced_state: State) -> None:
    s = synced_state
    wi = by_title(s, "Your BYOB leaderboard")
    actions.move_item(s, wi.id, None, "t")
    run_pipeline(s, fetched(), NOW, BASE)
    assert wi.course_id is None and wi.classification == "manual"


def test_status_toggle_is_sticky(synced_state: State) -> None:
    s = synced_state
    wi = by_title(s, "Framework Drill")  # Submitted on Nexus
    cs = actions.set_status(s, wi.id, "pending", "tok")
    run_pipeline(s, fetched(), NOW, BASE)
    assert wi.my_status == "pending" and wi.my_status_set_by == "user"
    actions.undo(s, _events(cs, "tok"), "tok")
    assert wi.my_status == "submitted"


def test_merge_repoints_sources_and_keeps_assignment_link(synced_state: State) -> None:
    s = synced_state
    keep = by_title(s, "Important: END TERM ASSIGNMENT")
    gone = by_title(s, "Rapido Pricing Memo")
    actions.merge_items(s, keep.id, gone.id)
    assert gone.id not in s.work_items and keep.assignment_raw_id is not None
    assert keep.origin == "both"
    cs, _ = run_pipeline(s, fetched(), NOW, BASE)
    assert not cs.work_items_insert  # the merged-away assignment is not recreated


def test_merge_two_assignments_refused(synced_state: State) -> None:
    s = synced_state
    with pytest.raises(actions.ActionError):
        actions.merge_items(s, by_title(s, "Zepto").id, by_title(s, "Rapido").id)


def test_undo_unknown_token() -> None:
    with pytest.raises(actions.ActionError):
        actions.undo(State(), [], "nope")
