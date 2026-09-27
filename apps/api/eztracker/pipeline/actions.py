"""User-intent mutations (move, status, overrides, merge, undo) as pure functions over State.

Every user action groups its events under one undo token. Undo replays `from_value` dicts in reverse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models import Alias, ChangeSet, Event, State, WorkItem, new_id
from .text import GENERIC_TERMS, STOPWORDS, normalize, significant_tokens

LEARNED_WEIGHT = 0.5
LEARN_DECREMENT = 0.25
MAX_LEARNED_TOKENS = 3


class ActionError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _ser(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _set(cs: ChangeSet, wi: WorkItem, **fields: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    frm, to = {}, {}
    for k, v in fields.items():
        old = getattr(wi, k)
        if old != v:
            frm[k], to[k] = _ser(old), _ser(v)
            setattr(wi, k, v)
            cs.work_items_update.setdefault(wi.id, {})[k] = v
    return frm, to


def _item(state: State, item_id: str) -> WorkItem:
    wi = state.work_items.get(item_id)
    if wi is None:
        raise ActionError("item not found", 404)
    return wi


# --------------------------------------------------------------------------- alias learning

def salient_tokens(title: str, course_id: str, state: State) -> list[str]:
    existing = {a.alias for a in state.aliases_for(course_id)}
    out: list[str] = []
    for t in significant_tokens(title):
        if t in STOPWORDS or t in GENERIC_TERMS or t in existing or t in out:
            continue
        out.append(t)
        if len(out) == MAX_LEARNED_TOKENS:
            break
    return out


def learn_from_move(state: State, cs: ChangeSet, wi: WorkItem, from_course: str | None,
                    to_course: str | None) -> dict[str, Any]:
    """Returns {'learned': [alias ids], 'decremented': {id: old_weight}, 'deleted': [Alias dicts]} for undo."""
    record: dict[str, Any] = {"learned": [], "decremented": {}, "deleted": []}
    title_n = normalize(wi.title)
    # 1. penalise learned aliases of the course we moved AWAY from that matched this title
    if from_course:
        for a in list(state.aliases_for(from_course)):
            if a.source == "learned" and f" {a.alias} " in f" {title_n} ":
                record["decremented"][a.id] = a.weight
                a.weight = round(a.weight - LEARN_DECREMENT, 3)
                if a.weight <= 0:
                    record["deleted"].append({"id": a.id, "course_id": a.course_id, "alias": a.alias,
                                              "source": a.source, "weight": record["decremented"].pop(a.id)})
                    del state.aliases[a.id]
                    cs.aliases_delete.add(a.id)
                    cs.aliases_update.pop(a.id, None)
                else:
                    cs.aliases_update[a.id] = a
    # 2. learn new tokens for the destination
    if to_course:
        for tok in salient_tokens(wi.title, to_course, state):
            a = Alias(new_id(), to_course, tok, "learned", LEARNED_WEIGHT)
            state.aliases[a.id] = a
            cs.aliases_insert[a.id] = a
            record["learned"].append(a.id)
    return record


# --------------------------------------------------------------------------- actions

def move_item(state: State, item_id: str, course_id: str | None, undo_token: str) -> ChangeSet:
    wi = _item(state, item_id)
    if course_id is not None and course_id not in state.courses:
        raise ActionError("course not found", 404)
    cs = ChangeSet()
    old_course = wi.course_id
    frm, to = _set(cs, wi, course_id=course_id,
                   classification="manual" if course_id else "unresolved",
                   confidence=1.0 if course_id else wi.confidence)
    if course_id is None:
        # Moving back to Needs Review is also a deliberate choice: keep it sticky.
        frm2, to2 = _set(cs, wi, classification="manual")
        frm.update({k: v for k, v in frm2.items() if k not in frm})
        to.update(to2)
    learned = learn_from_move(state, cs, wi, old_course, course_id) if old_course != course_id else {}
    to["_aliases"] = learned
    cs.events.append(Event(wi.id, "user", "moved", frm, to, undo_token))
    return cs


def set_status(state: State, item_id: str, my_status: str, undo_token: str) -> ChangeSet:
    wi = _item(state, item_id)
    cs = ChangeSet()
    frm, to = _set(cs, wi, my_status=my_status, my_status_set_by="user")
    cs.events.append(Event(wi.id, "user", "status_changed", frm, to, undo_token))
    return cs


def patch_item(state: State, item_id: str, patch: dict[str, Any], undo_token: str) -> ChangeSet:
    wi = _item(state, item_id)
    cs = ChangeSet()
    fields: dict[str, Any] = {}
    if "my_note" in patch:
        fields["my_note"] = patch["my_note"]
    if "title" in patch and patch["title"]:
        fields.update(title=patch["title"], title_source="user")
    if "kind" in patch and patch["kind"]:
        fields.update(kind=patch["kind"], kind_source="user")
    if "due_at" in patch:
        if patch.get("due_use_upstream"):
            fields.update(due_at=wi.upstream_due_at, due_source="nexus_field", upstream_due_at=None)
        else:
            fields.update(due_at=patch["due_at"], due_source="user")
    if "is_hidden" in patch:
        fields["is_hidden"] = bool(patch["is_hidden"])
        if not patch["is_hidden"]:
            fields["upstream_updated_at"] = None
    frm, to = _set(cs, wi, **fields)
    if frm:
        name = "hidden" if set(frm) == {"is_hidden"} else (
            "note_changed" if set(frm) == {"my_note"} else "edited")
        if "due_at" in frm:
            name = "due_changed"
        elif "title" in frm:
            name = "title_changed"
        cs.events.append(Event(wi.id, "user", name, frm, to, undo_token))
    return cs


def create_manual(state: State, data: dict[str, Any], undo_token: str) -> tuple[WorkItem, ChangeSet]:
    cs = ChangeSet()
    course_id = data.get("course_id")
    if course_id is not None and course_id not in state.courses:
        raise ActionError("course not found", 404)
    wi = WorkItem(
        id=new_id(), title=data["title"], origin="manual", kind=data.get("kind") or "assignment",
        course_id=course_id, due_at=data.get("due_at"), due_source="user" if data.get("due_at") else None,
        instructions_md=data.get("instructions_md"), my_note=data.get("my_note"),
        classification="manual", confidence=1.0, title_source="user", kind_source="user",
    )
    state.work_items[wi.id] = wi
    cs.work_items_insert[wi.id] = wi
    cs.events.append(Event(wi.id, "user", "created", None, {"title": wi.title}, undo_token))
    return wi, cs


def merge_items(state: State, keep_id: str, merge_id: str) -> ChangeSet:
    if keep_id == merge_id:
        raise ActionError("cannot merge an item with itself")
    keep, gone = _item(state, keep_id), _item(state, merge_id)
    if keep.assignment_raw_id and gone.assignment_raw_id:
        raise ActionError("both items are Nexus assignments; they cannot be merged", 409)
    cs = ChangeSet()
    for (w, nid) in list(state.sources):
        if w == merge_id:
            state.sources.discard((w, nid))
            cs.sources_delete.add((w, nid))
            if (keep_id, nid) not in state.sources:
                state.sources.add((keep_id, nid))
                cs.sources_insert.add((keep_id, nid))
    fields: dict[str, Any] = {}
    if gone.assignment_raw_id and not keep.assignment_raw_id:
        # the assignment link must survive, or the next sync would recreate the merged-away item
        fields["assignment_raw_id"] = gone.assignment_raw_id
        cs.work_items_update.setdefault(gone.id, {})["assignment_raw_id"] = None
        gone.assignment_raw_id = None
    has_assignment = bool(keep.assignment_raw_id or fields.get("assignment_raw_id"))
    has_notes = any(nid for (w, nid) in state.sources if w == keep_id)
    if has_assignment and has_notes:
        fields["origin"] = "both"
    if not keep.due_at and gone.due_at:
        fields.update(due_at=gone.due_at, due_source=gone.due_source)
    if gone.my_note:
        fields["my_note"] = "\n\n".join(x for x in [keep.my_note, gone.my_note] if x)
    frm, to = _set(cs, keep, **fields)
    to["merged_from"] = {"id": gone.id, "title": gone.title}
    cs.events.append(Event(keep.id, "user", "merged", frm, to, None))
    del state.work_items[merge_id]
    cs.work_items_delete.add(merge_id)
    return cs


_UNDOABLE = {"moved", "status_changed", "hidden", "note_changed", "edited", "due_changed", "title_changed"}


def undo(state: State, events: list[dict[str, Any]], undo_token: str) -> ChangeSet:
    """events: rows from work_item_events with this undo_token (newest first)."""
    cs = ChangeSet()
    if not events:
        raise ActionError("nothing to undo (token expired or unknown)", 410)
    for ev in events:
        if ev["event"] not in _UNDOABLE:
            continue
        wi = state.work_items.get(ev["work_item_id"])
        if wi is None:
            continue
        frm: dict[str, Any] = ev.get("from_value") or {}
        restore = {}
        for k, v in frm.items():
            if k in {"due_at", "upstream_due_at", "upstream_updated_at", "due_changed_at"} and isinstance(v, str):
                v = datetime.fromisoformat(v)
            restore[k] = v
        f2, t2 = _set(cs, wi, **restore)
        aliases = (ev.get("to_value") or {}).get("_aliases") or {}
        for aid in aliases.get("learned", []):
            if aid in state.aliases:
                del state.aliases[aid]
                cs.aliases_delete.add(aid)
        for aid, w in (aliases.get("decremented") or {}).items():
            if aid in state.aliases:
                state.aliases[aid].weight = w
                cs.aliases_update[aid] = state.aliases[aid]
        for d in aliases.get("deleted", []):
            a = Alias(d["id"], d["course_id"], d["alias"], d["source"], d["weight"])
            state.aliases[a.id] = a
            cs.aliases_insert[a.id] = a
        cs.events.append(Event(wi.id, "user", "undo", f2, t2, None))
    return cs
