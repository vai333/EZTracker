"""Deterministic weighted classifier (§7). Honest about uncertainty: low confidence → Needs Review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from rapidfuzz import fuzz

from ..models import NotificationRow, State, WorkItem
from .dates import extract_due
from .normalize import course_acronyms, course_core_name, course_people, notification_display_title
from .text import GENERIC_TERMS, contains_phrase, normalize, significant_tokens, stem, stems

NAME_FILLER = frozenset({"and", "of", "its", "the", "with", "a", "an", "for", "to", "in", "on"})

W_FULL_NAME = 0.6
W_ALIAS = 0.25
W_ALIAS_CAP = 0.5
W_INSTRUCTOR = 0.3
W_LINK_ID = 0.8
W_TITLE_SIM = 0.5
W_GENERIC_PENALTY = -0.3
TITLE_SIM_THRESHOLD = 85

AUTO_CONFIDENCE = 0.70
AUTO_MARGIN = 0.20

_DELIVERABLE = re.compile(
    r"\b(assignments?|workbooks?|submit|submission|submissions|deadline|due|end[\s-]?term|quiz(?:zes)?|exams?|"
    r"opt[\s-]?in|deliverables?|upload|assessments?|mid[\s-]?term|viva|presentation deck)\b",
    re.I,
)
_TITLE_NOISE = re.compile(r"^(important|reminder|update|new|urgent|fyi)\s*[:\-–—]\s*", re.I)


@dataclass
class Candidate:
    course_id: str
    course: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def add(self, w: float, why: str) -> None:
        self.score += w
        self.reasons.append(f"{why} ({'+' if w >= 0 else ''}{w:.2f})")


@dataclass
class Classification:
    course_id: str | None
    confidence: float
    classification: str                 # auto | unresolved
    reasons: list[dict[str, Any]]       # top-2 candidates, structured for the UI
    linked_work_item_id: str | None
    is_task: bool
    kind: str
    due_at: datetime | None
    title: str


class Classifier(Protocol):
    def classify(self, n: NotificationRow, state: State) -> Classification: ...


def clean_title(t: str) -> str:
    return _TITLE_NOISE.sub("", t or "").strip()


def infer_kind(text: str, has_date: bool, category_raw: str | None) -> tuple[bool, str]:
    n = normalize(text)
    task_score = 0.0
    if _DELIVERABLE.search(n):
        task_score += 0.5
    if has_date:
        task_score += 0.5
    if normalize(category_raw) == "assignment":
        task_score += 0.1
    if task_score < 0.5:
        return False, "info"
    if re.search(r"\bworkbooks?\b", n):
        return True, "workbook"
    if re.search(r"\b(quiz|quizzes|exam|exams|viva|mid ?term)\b", n):
        return True, "exam"
    if re.search(r"\b(form|opt ?in|survey)\b", n):
        return True, "form"
    if re.search(r"\basync\b", n):
        return True, "async_assignment"
    return True, "announcement_task"


def kind_for_assignment(title: str, type_raw: str | None) -> str:
    n = normalize(f"{title} {type_raw or ''}")
    if re.search(r"\bworkbooks?\b", n):
        return "workbook"
    if re.search(r"\basync\b", n):
        return "async_assignment"
    if re.search(r"\b(form|opt ?in)\b", n):
        return "form"
    if re.search(r"\b(quiz|exam|viva)\b", n):
        return "exam"
    return "assignment"


class DeterministicClassifier:
    def classify(self, n: NotificationRow, state: State) -> Classification:
        title = notification_display_title(n.title, n.snippet)
        body_text = re.sub(r"<[^>]+>", " ", n.body_html or "")
        full_text = " ".join(x for x in [n.title, n.snippet, body_text] if x)
        text_n = normalize(full_text)
        text_stems = stems(full_text)

        cands: dict[str, Candidate] = {}
        active = [c for c in state.courses.values() if not c.is_archived]

        def cand(cid: str) -> Candidate:
            if cid not in cands:
                cands[cid] = Candidate(cid, state.courses[cid].short_name or state.courses[cid].name)
            return cands[cid]

        for c in active:
            core = course_core_name(c.name)
            core_stems = {stem(t) for t in normalize(core).split() if t not in NAME_FILLER}
            if core_stems and len(core_stems) >= 2 and core_stems <= text_stems:
                cand(c.id).add(W_FULL_NAME, f"course name '{core}'")
            else:
                for label in [c.short_name, *course_acronyms(c.name)]:
                    if label and len(label) >= 3 and contains_phrase(text_n, label):
                        cand(c.id).add(W_FULL_NAME, f"course reference '{label}'")
                        break

            people = set(course_people(c.name, c.instructor))
            if any(contains_phrase(text_n, p) for p in people):
                hit = next(p for p in people if contains_phrase(text_n, p))
                cand(c.id).add(W_INSTRUCTOR, f"instructor '{hit}'")

            alias_total = 0.0
            for a in state.aliases_for(c.id):
                if a.alias in people or a.weight <= 0:
                    continue
                if contains_phrase(text_n, a.alias) and alias_total < W_ALIAS_CAP:
                    w = min(W_ALIAS * a.weight, W_ALIAS_CAP - alias_total)
                    alias_total += w
                    cand(c.id).add(w, f"alias '{a.alias}'" + (" (learned)" if a.source == "learned" else ""))

            # §7 "known course id": Nexus names the course in the notification's data, or in its link
            data = (n.payload or {}).get("data")
            ext_course = data.get("courseId") if isinstance(data, dict) else None
            if c.nexus_course_id and (ext_course == c.nexus_course_id
                                      or (n.link_url and c.nexus_course_id in n.link_url)):
                cand(c.id).add(W_LINK_ID, "Nexus names this course")

        # 1) exact: Nexus names the assignment (data.assignmentId, or its id in the link)
        # 2) otherwise: title similarity to an existing assignment → link to that work item
        linked: WorkItem | None = None
        data_a = (n.payload or {}).get("data")
        ext_a = data_a.get("assignmentId") if isinstance(data_a, dict) else None
        for wi in state.work_items.values():
            raw = state.assignments.get(wi.assignment_raw_id) if wi.assignment_raw_id else None
            if raw and ((ext_a and raw.nexus_assignment_id == ext_a)
                        or (n.link_url and raw.nexus_assignment_id in n.link_url)):
                linked = wi
                break
        ct = normalize(clean_title(title))
        if linked is None and len(significant_tokens(ct)) >= 2:
            best_sim = 0.0
            for wi in state.work_items.values():
                if wi.assignment_raw_id is None:
                    continue
                sim = fuzz.token_set_ratio(ct, normalize(clean_title(wi.title)))
                # token_set_ratio is 100 for any subset; demand real overlap of meaningful words
                overlap = set(significant_tokens(ct)) & set(significant_tokens(wi.title))
                if len(overlap) < 2:
                    sim = min(sim, 70)
                if sim >= TITLE_SIM_THRESHOLD and sim > best_sim:
                    best_sim, linked = sim, wi
        if linked and linked.course_id:
            cand(linked.course_id).add(W_TITLE_SIM, f"matches assignment '{linked.title[:40]}'")

        # generic, institution-wide wording with no explicit course hit
        has_course_hit = any(any("course" in r.lower() for r in cd.reasons) for cd in cands.values())
        if not has_course_hit and set(normalize(title).split()) & GENERIC_TERMS:
            for cd in cands.values():
                cd.add(W_GENERIC_PENALTY, "institution-wide wording")

        ranked = sorted(cands.values(), key=lambda cd: cd.score, reverse=True)
        best = ranked[0] if ranked else None
        second = ranked[1].score if len(ranked) > 1 else 0.0
        confidence = max(0.0, min(1.0, best.score)) if best else 0.0
        margin = (best.score - second) if best else 0.0
        auto = best is not None and confidence >= AUTO_CONFIDENCE and margin >= AUTO_MARGIN

        due = extract_due(full_text, n.published_at)
        is_task, kind = infer_kind(full_text, due is not None, n.category_raw)
        if linked is not None:
            is_task, kind = True, linked.kind

        return Classification(
            course_id=best.course_id if auto and best else None,
            confidence=round(confidence, 3),
            classification="auto" if auto else "unresolved",
            reasons=[{"course_id": c.course_id, "course": c.course, "score": round(c.score, 3),
                      "reasons": c.reasons} for c in ranked[:2] if c.score > 0],
            linked_work_item_id=linked.id if linked else None,
            is_task=is_task,
            kind=kind,
            due_at=due,
            title=title,
        )


def default_classifier() -> Classifier:
    """Feature-flag seam for a future LLM classifier (§13). v1 ships deterministic only."""
    return DeterministicClassifier()
