from datetime import UTC, datetime

import pytest

from eztracker.pipeline.dates import IST, extract_due, parse_absolute, resolve_relative

SCRAPED = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)   # Sun 27 Sep 2026 11:30 IST
PUBLISHED = datetime(2026, 9, 25, 6, 0, tzinfo=UTC)  # Fri 25 Sep 2026


def ist(dt: datetime | None) -> str | None:
    return dt.astimezone(IST).strftime("%a %d %b %Y %H:%M") if dt else None


@pytest.mark.parametrize("label,expected", [
    ("Yesterday", "Sat 26 Sep 2026 00:00"),
    ("Fri", "Fri 25 Sep 2026 00:00"),
    ("Sun", "Sun 20 Sep 2026 00:00"),          # bare weekday = most recent PAST one
    ("2h ago", "Sun 27 Sep 2026 09:30"),
    ("15 min ago", "Sun 27 Sep 2026 11:15"),
    ("Today, 10:15 AM", "Sun 27 Sep 2026 10:15"),
    ("12 Sep", "Sat 12 Sep 2026 00:00"),
    ("28 Dec", "Sun 28 Dec 2025 00:00"),       # future-looking month in a feed rolls back a year
])
def test_resolve_relative(label: str, expected: str) -> None:
    assert ist(resolve_relative(label, SCRAPED)) == expected


@pytest.mark.parametrize("text,expected", [
    ("Submit by 30th Sept", "Wed 30 Sep 2026 23:59"),
    ("Due 30/09", "Wed 30 Sep 2026 23:59"),
    ("Please upload before 11:59 PM on Tuesday.", "Tue 29 Sep 2026 23:59"),
    ("deadline: Oct 3, 5pm", "Sat 03 Oct 2026 17:00"),
    ("Submit your end term deck by 5th Oct, 11:59 PM.", "Mon 05 Oct 2026 23:59"),
    ("Submissions close on 2 January", "Sat 02 Jan 2027 23:59"),
    ("due tomorrow at 9 am", "Sat 26 Sep 2026 09:00"),
])
def test_extract_due(text: str, expected: str) -> None:
    assert ist(extract_due(text, PUBLISHED)) == expected


@pytest.mark.parametrize("text", [
    "Session 7 Marketing Workbook",            # 'mar' must not become March
    "Session on 12 Sep. Bring laptops",        # a date without a deadline trigger
    "Talk by Prof. Sharma this month",         # 'mon'th is not Monday
    "CLUBS ARE FINALLY HERE!",
])
def test_extract_due_ignores_non_deadlines(text: str) -> None:
    assert extract_due(text, PUBLISHED) is None


def test_parse_absolute() -> None:
    assert parse_absolute("2026-09-30T18:29:00.000Z") == datetime(2026, 9, 30, 18, 29, tzinfo=UTC)
    assert parse_absolute(1790000000000) == datetime.fromtimestamp(1790000000, UTC)
    assert parse_absolute("2026-09-30T23:59:00") == datetime(2026, 9, 30, 18, 29, tzinfo=UTC)  # naive = IST
    assert parse_absolute(None) is None
