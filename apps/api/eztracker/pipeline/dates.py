"""Relative-timestamp resolution and due-date extraction. All results are timezone-aware UTC.

Everything is resolved in Asia/Kolkata (Nexus's wall clock) and converted to UTC for storage.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import dateparser

IST = ZoneInfo("Asia/Kolkata")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
        r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?")
_WD = (r"(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|"
       r"sun(?:day)?)")
_ORD = r"(?:st|nd|rd|th)?"

_RE_DMY_WORD = re.compile(rf"\b(\d{{1,2}}){_ORD}\s*(?:of\s+)?{_MON}(?:,?\s*(\d{{4}}))?", re.I)
_RE_MDY_WORD = re.compile(rf"\b{_MON}\s+(\d{{1,2}}){_ORD}(?:,?\s*(\d{{4}}))?", re.I)
_RE_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b")
_RE_WEEKDAY = re.compile(rf"\b(next\s+)?{_WD}\b", re.I)
_RE_REL_DAY = re.compile(r"\b(today|tonight|tomorrow|eod|end of (?:the )?day)\b", re.I)
_RE_TIME_12 = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\.?", re.I)
_RE_TIME_24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*[ap]\.?m)", re.I)
_RE_MIDNIGHT = re.compile(r"\bmidnight\b", re.I)
_RE_NOON = re.compile(r"\bnoon\b", re.I)

_DUE_TRIGGER = re.compile(
    r"\b(due(?:\s+date)?|deadline|submit(?:\s+\w+){0,4}?\s+by|by|before|latest\s+by|no\s+later\s+than|"
    r"on\s+or\s+before|till|until|closes?(?:\s+on)?|last\s+date(?:\s+to\s+\w+)?|submission(?:\s+date)?)\b[:\s]*",
    re.I,
)
_WINDOW = 70
DEFAULT_DUE_TIME = time(23, 59)


def now_ist() -> datetime:
    return datetime.now(IST)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


# --------------------------------------------------------------------------- relative timestamps

_RE_AGO = re.compile(r"(\d+)\s*(s|sec|second|m|min|minute|h|hr|hour|d|day|w|week)s?\s*ago", re.I)


def resolve_relative(label: str | None, scraped_at: datetime) -> datetime | None:
    """Resolve Nexus labels like 'Yesterday', 'Fri', '2h ago', '12 Sep' against scrape time (IST)."""
    if not label:
        return None
    s = label.strip().lower()
    base = scraped_at.astimezone(IST)
    if s in {"now", "just now"}:
        return to_utc(base)
    if m := _RE_AGO.search(s):
        n, unit = int(m.group(1)), m.group(2)[0]
        delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n), "h": timedelta(hours=n),
                 "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
        return to_utc(base - delta)
    t = _parse_time(s) or time(0, 0)
    if s.startswith("today"):
        return to_utc(datetime.combine(base.date(), t, IST))
    if s.startswith("yesterday"):
        return to_utc(datetime.combine(base.date() - timedelta(days=1), t, IST))
    d = _parse_date_expr(s, base.date(), prefer="past", weekdays=False)
    if d:
        return to_utc(datetime.combine(d, t, IST))
    if m := re.match(rf"{_WD}\b", s):
        wd = _WEEKDAYS[m.group(1)[:3]]
        back = (base.weekday() - wd) % 7 or 7  # a bare weekday in a feed means the most recent past one
        return to_utc(datetime.combine(base.date() - timedelta(days=back), t, IST))
    parsed = dateparser.parse(label, settings={"RELATIVE_BASE": base.replace(tzinfo=None),
                                               "PREFER_DATES_FROM": "past", "TIMEZONE": "Asia/Kolkata",
                                               "RETURN_AS_TIMEZONE_AWARE": True, "DATE_ORDER": "DMY"})
    return parsed.astimezone(UTC) if parsed else None


def parse_absolute(value: object) -> datetime | None:
    """Parse an absolute timestamp from JSON (ISO string or epoch)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        secs = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(secs, UTC)
    if isinstance(value, str):
        v = value.strip()
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return to_utc(dt)
        except ValueError:
            parsed = dateparser.parse(v, settings={"TIMEZONE": "Asia/Kolkata", "RETURN_AS_TIMEZONE_AWARE": True,
                                                   "DATE_ORDER": "DMY"})
            return parsed.astimezone(UTC) if parsed else None
    return None


# --------------------------------------------------------------------------- due-date extraction

def _parse_time(s: str) -> time | None:
    if _RE_MIDNIGHT.search(s):
        return time(23, 59)
    if _RE_NOON.search(s):
        return time(12, 0)
    if m := _RE_TIME_12.search(s):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if 1 <= h <= 12 and mi < 60:
            h = h % 12 + (12 if ap == "p" else 0)
            return time(h, mi)
    if m := _RE_TIME_24.search(s):
        return time(int(m.group(1)), int(m.group(2)))
    return None


def _roll_year(month: int, day: int, year: int | None, ref: date, prefer: str) -> date | None:
    try:
        if year:
            return date(year if year > 100 else 2000 + year, month, day)
        d = date(ref.year, month, day)
    except ValueError:
        return None
    if prefer == "future" and d < ref - timedelta(days=7):
        d = d.replace(year=d.year + 1)
    elif prefer == "past" and d > ref + timedelta(days=1):
        d = d.replace(year=d.year - 1)
    return d


def _parse_date_expr(s: str, ref: date, prefer: str = "future", weekdays: bool = True) -> date | None:
    if m := _RE_DMY_WORD.search(s):
        return _roll_year(_MONTHS[m.group(2)[:3].lower()], int(m.group(1)),
                          int(m.group(3)) if m.group(3) else None, ref, prefer)
    if m := _RE_MDY_WORD.search(s):
        return _roll_year(_MONTHS[m.group(1)[:3].lower()], int(m.group(2)),
                          int(m.group(3)) if m.group(3) else None, ref, prefer)
    if m := _RE_NUMERIC.search(s):
        d_, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d_ <= 31:
            return _roll_year(mo, d_, int(m.group(3)) if m.group(3) else None, ref, prefer)
    if m := _RE_REL_DAY.search(s):
        word = m.group(1).lower()
        return ref + timedelta(days=1) if word == "tomorrow" else ref
    if weekdays and (m := _RE_WEEKDAY.search(s)):
        wd = _WEEKDAYS[m.group(2)[:3].lower()]
        ahead = (wd - ref.weekday()) % 7
        if m.group(1):
            ahead = ahead or 7
        return ref + timedelta(days=ahead)
    return None


def extract_due(text: str | None, published_at: datetime | None) -> datetime | None:
    """Find a deadline in free text, e.g. 'by 30th Sept', 'due 30/09', 'before 11:59 PM on Tuesday'.

    Only dates that follow a deadline trigger word are considered, so a session date mentioned in passing
    ("Session on 12 Sep") is not mistaken for a due date. Returns UTC or None.
    """
    if not text:
        return None
    ref_dt = (published_at or datetime.now(UTC)).astimezone(IST)
    flat = " ".join(text.split())
    for trig in _DUE_TRIGGER.finditer(flat):
        window = flat[trig.end(): trig.end() + _WINDOW]
        # stop the window at a sentence boundary so we don't borrow a date from the next sentence
        window = re.split(r"(?<=[a-z0-9)])[.!?]\s+[A-Z]", window)[0]
        d = _parse_date_expr(window, ref_dt.date(), prefer="future")
        t = _parse_time(window)
        if d is None and t is not None:
            # "by 11:59 PM" with the date just before the trigger: look back a little
            back = flat[max(0, trig.start() - 40): trig.start()]
            d = _parse_date_expr(back, ref_dt.date(), prefer="future") or ref_dt.date()
        if d is not None:
            return to_utc(datetime.combine(d, t or DEFAULT_DUE_TIME, IST))
    return None
