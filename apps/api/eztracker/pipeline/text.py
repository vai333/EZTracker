"""Text normalization shared by normalize, classify and alias learning."""

import hashlib
import json
import re
import unicodedata
from typing import Any

import nh3
from markdownify import markdownify

STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or the to with your you our we this that
    will can all new prof dr mr ms mrs sir maam session sessions course courses class classes week term
    important update updated reminder please note details detail regarding re fwd info information today
    tomorrow yesterday via using own build about into out up""".split()
)

# Institution-wide words: never learned as aliases, and penalised when they are the only signal (§7).
GENERIC_TERMS = frozenset(
    """clubs club leaderboard panel career careers placement placements mesa cohort batch pgp orientation
    event events celebration fest community townhall town hall survey feedback holiday library hostel
    campus guest speaker talk announcement assignment assignments form forms workbook group groups""".split()
)

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("&", " and ").replace("_", " ")
    t = _PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokens(text: str | None) -> list[str]:
    return normalize(text).split()


def stems(text: str | None) -> set[str]:
    return {stem(t) for t in tokens(text)}


def significant_tokens(text: str | None) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 2 and not t.isdigit()]


def contains_phrase(haystack_norm: str, phrase: str) -> bool:
    """Word-boundary match of a normalized phrase inside normalized text."""
    p = normalize(phrase)
    return bool(p) and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", haystack_norm) is not None


def content_hash(fields: dict[str, Any]) -> str:
    blob = json.dumps(fields, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def html_to_markdown(html: str | None) -> str | None:
    if not html:
        return None
    clean = nh3.clean(html, tags={"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "a", "h1", "h2",
                                   "h3", "h4", "table", "thead", "tbody", "tr", "td", "th", "blockquote",
                                   "code", "pre", "span", "div"})
    md: str = markdownify(clean, heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md or None
