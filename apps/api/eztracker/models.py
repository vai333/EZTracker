"""Domain records. Raw* = what a scraper adapter returns. Row types mirror DB tables.

The pipeline is a functional core: it takes a `State` (rows loaded from the DB) plus freshly fetched raw
records, mutates an in-memory copy, and records every change in a `ChangeSet` that the DB layer applies.
This makes idempotence and the sticky rules testable without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Surface = Literal["courses", "assignments", "notifications"]


def new_id() -> str:
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------- raw records (adapter output)

@dataclass
class RawCourse:
    name: str
    nexus_course_id: str | None = None
    instructor: str | None = None
    category: str | None = None
    mode: str | None = None
    term: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    short_name: str | None = None
    visible: bool = True        # Nexus hides some courses (visible:false); EZTracker creates those archived


@dataclass
class RawAssignment:
    nexus_assignment_id: str
    title: str
    course_name_raw: str | None = None
    type_raw: str | None = None
    due_at: datetime | None = None
    status_raw: str | None = None
    description_html: str | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawNotification:
    nexus_notification_id: str
    title: str | None = None
    category_raw: str | None = None
    snippet: str | None = None
    body_html: str | None = None
    published_at: datetime | None = None
    is_unread_on_nexus: bool | None = None
    link_url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


RawRecord = RawCourse | RawAssignment | RawNotification


# ----------------------------------------------------------------------------- DB rows

@dataclass
class Course:
    id: str
    name: str
    nexus_course_id: str | None = None
    short_name: str | None = None
    instructor: str | None = None
    category: str = "other"
    mode: str | None = None
    term: str | None = None
    color_index: int = 0
    is_archived: bool = False


@dataclass
class Alias:
    id: str
    course_id: str
    alias: str
    source: str = "seed"
    weight: float = 1.0


@dataclass
class AssignmentRow:
    id: str
    nexus_assignment_id: str
    title: str
    content_hash: str
    course_name_raw: str | None = None
    type_raw: str | None = None
    due_at: datetime | None = None
    status_raw: str | None = None
    description_html: str | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationRow:
    id: str
    nexus_notification_id: str
    content_hash: str
    title: str | None = None
    category_raw: str | None = None
    snippet: str | None = None
    body_html: str | None = None
    published_at: datetime | None = None
    is_unread_on_nexus: bool | None = None
    link_url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkItem:
    id: str
    title: str
    origin: str
    kind: str = "info"
    course_id: str | None = None
    due_at: datetime | None = None
    due_source: str | None = None
    instructions_md: str | None = None
    links: list[dict[str, str]] = field(default_factory=list)
    nexus_status: str | None = None
    my_status: str = "pending"
    my_status_set_by: str = "default"
    my_note: str | None = None
    classification: str = "unresolved"
    confidence: float | None = None
    classifier_reasons: list[dict[str, Any]] = field(default_factory=list)
    assignment_raw_id: str | None = None
    is_hidden: bool = False
    title_source: str = "nexus"
    kind_source: str = "auto"
    upstream_due_at: datetime | None = None
    due_changed_at: datetime | None = None
    upstream_updated_at: datetime | None = None


@dataclass
class Event:
    work_item_id: str
    actor: Literal["scraper", "user"]
    event: str
    from_value: Any = None
    to_value: Any = None
    undo_token: str | None = None


@dataclass
class State:
    courses: dict[str, Course] = field(default_factory=dict)
    aliases: dict[str, Alias] = field(default_factory=dict)
    assignments: dict[str, AssignmentRow] = field(default_factory=dict)      # by row id
    notifications: dict[str, NotificationRow] = field(default_factory=dict)  # by row id
    work_items: dict[str, WorkItem] = field(default_factory=dict)
    sources: set[tuple[str, str]] = field(default_factory=set)               # (work_item_id, notification_id)

    def assignment_by_ext(self, ext_id: str) -> AssignmentRow | None:
        return next((a for a in self.assignments.values() if a.nexus_assignment_id == ext_id), None)

    def notification_by_ext(self, ext_id: str) -> NotificationRow | None:
        return next((n for n in self.notifications.values() if n.nexus_notification_id == ext_id), None)

    def aliases_for(self, course_id: str) -> list[Alias]:
        return [a for a in self.aliases.values() if a.course_id == course_id]


@dataclass
class ChangeSet:
    """Everything a sync or a user action changed. The DB layer applies it in one transaction."""
    courses_upsert: dict[str, Course] = field(default_factory=dict)
    aliases_insert: dict[str, Alias] = field(default_factory=dict)
    aliases_update: dict[str, Alias] = field(default_factory=dict)
    aliases_delete: set[str] = field(default_factory=set)
    assignments_upsert: dict[str, AssignmentRow] = field(default_factory=dict)
    assignments_touch: set[str] = field(default_factory=set)       # unchanged, bump last_seen_at
    notifications_upsert: dict[str, NotificationRow] = field(default_factory=dict)
    notifications_touch: set[str] = field(default_factory=set)
    work_items_insert: dict[str, WorkItem] = field(default_factory=dict)
    work_items_update: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> changed fields
    work_items_delete: set[str] = field(default_factory=set)
    sources_insert: set[tuple[str, str]] = field(default_factory=set)
    sources_delete: set[tuple[str, str]] = field(default_factory=set)
    events: list[Event] = field(default_factory=list)

    def is_empty_of_writes(self) -> bool:
        """True when nothing but last_seen_at touches happened (the idempotence criterion)."""
        return not (self.courses_upsert or self.aliases_insert or self.aliases_update or self.aliases_delete
                    or self.assignments_upsert or self.notifications_upsert or self.work_items_insert
                    or self.work_items_update or self.work_items_delete or self.sources_insert
                    or self.sources_delete or self.events)
