"""raw → canonical: content hashes, course name anatomy, seed aliases."""

import re

from ..models import RawAssignment, RawCourse, RawNotification
from .text import GENERIC_TERMS, STOPWORDS, content_hash, normalize, significant_tokens

_WITH = re.compile(r"\s+with\s+(?:prof\.?|dr\.?|mr\.?|ms\.?)?\s*(.+)$", re.I)
_PARENS = re.compile(r"\(([^)]*)\)")
_HONORIFIC = re.compile(r"\b(prof|dr|mr|ms|mrs|sir)\b\.?", re.I)

# Case companies seen in DDDM so far — used to seed aliases the first time the course appears (§6.2).
KNOWN_CASE_COMPANIES = ["zepto", "urban company", "rapido", "blinkit", "lenskart", "cultfit", "cult fit",
                        "swiggy", "zomato", "nykaa", "meesho"]

GENERIC_TITLES = {"new announcement", "new assignment", "announcement", "new notification", "reminder",
                  "new form", "update", "new message"}


def assignment_hash(r: RawAssignment) -> str:
    return content_hash({"title": r.title, "course": r.course_name_raw, "type": r.type_raw, "due": r.due_at,
                         "status": r.status_raw, "desc": r.description_html, "att": r.attachments, "url": r.url})


def notification_hash(r: RawNotification) -> str:
    return content_hash({"title": r.title, "cat": r.category_raw, "snippet": r.snippet, "body": r.body_html,
                         "pub": r.published_at, "link": r.link_url})


def notification_display_title(r_title: str | None, snippet: str | None) -> str:
    """Nexus titles are often generic ('New announcement'); the snippet carries the real subject."""
    t = (r_title or "").strip()
    s = (snippet or "").strip()
    if (not t or normalize(t) in GENERIC_TITLES) and s:
        first = re.split(r"[\n\r]", s)[0].strip()
        return first[:200]
    return t or s[:200] or "Untitled notification"


def course_core_name(name: str) -> str:
    """'Crafting Marketing Strategies with Prof. Siddarth Menon' → 'Crafting Marketing Strategies'."""
    core = _WITH.sub("", name)
    core = _PARENS.sub("", core)
    return re.sub(r"\s+", " ", core).strip(" -–—:")


def course_people(name: str, instructor: str | None) -> list[str]:
    """Instructor name tokens from the card field and from 'with Prof. X' / '(A & B)' in the name."""
    chunks: list[str] = []
    if instructor:
        chunks.append(instructor)
    if m := _WITH.search(name):
        chunks.append(m.group(1))
    for p in _PARENS.findall(name):
        if not re.fullmatch(r"[A-Z]{2,6}", p.strip()):  # '(BYOB)' is an acronym, not a person
            chunks.append(p)
    people: list[str] = []
    for c in chunks:
        for tok in normalize(_HONORIFIC.sub(" ", c)).split():
            if len(tok) > 2 and tok not in STOPWORDS and tok not in people:
                people.append(tok)
    return people


def course_acronyms(name: str) -> list[str]:
    out: list[str] = []
    for p in _PARENS.findall(name):
        if re.fullmatch(r"[A-Za-z]{2,6}", p.strip()):
            out.append(p.strip().lower())
    words = [w for w in normalize(course_core_name(name)).split() if w not in {"and", "of", "its", "the", "with"}]
    if len(words) >= 3:
        acro = "".join(w[0] for w in words)
        if acro not in out:
            out.append(acro)
    return out


def default_short_name(name: str) -> str:
    acr = course_acronyms(name)
    if acr:
        return acr[0].upper()
    core = course_core_name(name)
    return core if len(core) <= 18 else core[:16].rstrip() + "…"


def seed_aliases(course: RawCourse, all_course_names: list[str],
                 assignment_titles: list[str]) -> list[tuple[str, float]]:
    """Aliases for a newly seen course: distinctive name tokens, acronyms, instructor names, case companies.

    A name token is distinctive only if no other course's name contains it (so 'business' is never an alias).
    """
    out: dict[str, float] = {}
    others = [set(significant_tokens(course_core_name(n))) for n in all_course_names if n != course.name]
    shared = set().union(*others) if others else set()
    for tok in significant_tokens(course_core_name(course.name)):
        if tok not in shared and tok not in GENERIC_TERMS:
            out[tok] = 1.0
    core_phrase = normalize(course_core_name(course.name))
    if len(core_phrase.split()) >= 2:
        out[core_phrase] = 1.0  # the course's own name is its strongest alias
    for a in course_acronyms(course.name):
        out[a] = 1.0
    for p in course_people(course.name, course.instructor):
        out.setdefault(p, 1.0)
    blob = normalize(" ".join(assignment_titles))
    for co in KNOWN_CASE_COMPANIES:
        if re.search(rf"(?<!\w){re.escape(co)}(?!\w)", blob):
            out[co] = 1.0
    return list(out.items())


def category_of(raw: str | None) -> str:
    n = normalize(raw)
    if "core" in n:
        return "core"
    if "soft" in n:
        return "soft_skills"
    if "elective" in n:
        return "elective"
    return "other"
