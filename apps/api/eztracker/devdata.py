"""Dev/test data: Nexus-shaped fixtures mirroring the real courses, assignments and notifications in the brief."""

from datetime import UTC, datetime, timedelta

from eztracker.models import RawAssignment, RawCourse, RawNotification

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)  # Sun 27 Sep 2026, 11:30 IST
BASE = "https://students.mesaschool.co.in"

COURSES = [
    RawCourse("AI and its Application (Divij & Mihirr)", "c-ai", None, "Core", "Hybrid", "Term 1"),
    RawCourse("AI Workshops", "c-aiw", None, "Soft Skills", "In Class", "Term 1"),
    RawCourse("Build Your Own Business (BYOB)", "c-byob", None, "Core", "In Class", "Term 1"),
    RawCourse("Business Frameworks with Pranjal Bangani", "c-bf", None, "Core", "In Class", "Term 1"),
    RawCourse("Business Reader with Suprad", "c-br", None, "Soft Skills", "In Class", "Term 1"),
    RawCourse("Career Readiness", "c-cr", None, "Soft Skills", "Hybrid", "Term 1"),
    RawCourse("Crafting Marketing Strategies with Prof. Siddarth Menon", "c-cms", None, "Core", "In Class", "Term 1"),
    RawCourse("Data Driven Decision Making with Prof. Vinay Sharma", "c-dddm", None, "Core", "In Class", "Term 1"),
    RawCourse("Orientation Week", "c-ow", None, "Soft Skills", "In Class", "Pre-Term"),
]


def _due(days: int) -> datetime:
    return NOW + timedelta(days=days)


ASSIGNMENTS = [
    RawAssignment("a-1", "Zepto Case Analysis", "Data Driven Decision Making with Prof. Vinay Sharma",
                  "Individual", _due(3), "Pending", "<p>Analyse the <b>Zepto</b> dark-store economics.</p>"),
    RawAssignment("a-2", "Session 7 Lenskart Workbook", "Data Driven Decision Making with Prof. Vinay Sharma",
                  "Individual", _due(5), "Pending", "<p>Complete the workbook.</p>"),
    RawAssignment("a-3", "Rapido Pricing Memo", "Data Driven Decision Making with Prof. Vinay Sharma",
                  "Group", _due(-1), "Pending", None),
    RawAssignment("a-4", "BYOB Milestone 2: Customer Discovery", "Build Your Own Business (BYOB)",
                  "Group", _due(9), "Pending", "<p>Interview 15 customers.</p>"),
    RawAssignment("a-5", "Framework Drill: Porter's Five Forces", "Business Frameworks with Pranjal Bangani",
                  "Individual", _due(1), "Submitted", None),
]


def notif(ext: str, title: str, snippet: str, category: str, days_ago: float = 1, body: str | None = None,
          link: str | None = None) -> RawNotification:
    return RawNotification(ext, title, category, snippet, body, NOW - timedelta(days=days_ago), True, link)


NOTIFICATIONS = [
    notif("n-1", "New announcement", "Session 7 Lenskart Workbook", "Announcement"),
    notif("n-2", "New announcement", "Important: END TERM ASSIGNMENT – Crafting Marketing Strategy",
          "Announcement", body="<p>Submit your end term deck by 5th Oct, 11:59 PM.</p>"),
    notif("n-3", "New announcement", "Important: Assessment Details for Business Reader course", "Announcement"),
    notif("n-4", "New announcement", "Start-up Leader Session: Final Groups", "General"),
    notif("n-5", "New announcement", "CLUBS ARE FINALLY HERE!", "General"),
    notif("n-6", "Your BYOB leaderboard has been updated", "Check where your team stands.", "General"),
    notif("n-7", "New announcement", "Growth & GTM: 'What Is' Panel", "Announcement"),
    notif("n-8", "New assignment", "Zepto Case Analysis", "Assignment", days_ago=4),
]
