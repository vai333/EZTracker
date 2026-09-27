"""MongoDB Atlas data access. The only module that talks to the database.

Collections (all documents carry `user_id`; every query filters on it — the browser never talks to Mongo):
  users, courses, course_aliases, nexus_assignments_raw, nexus_notifications_raw, work_items,
  work_item_sources, work_item_events, nexus_credentials, sync_runs, user_settings, locks

Ids are UUID strings stored in `_id` (the pipeline generates them), exposed to callers as `id`.
A ChangeSet is applied inside one multi-document transaction (Atlas is a replica set).
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from .config import get_settings
from .models import Alias, AssignmentRow, ChangeSet, Course, NotificationRow, State, WorkItem

_client: AsyncMongoClient[dict[str, Any]] | None = None

WORK_ITEM_FIELDS = [
    "title", "origin", "kind", "course_id", "due_at", "due_source", "instructions_md", "links", "nexus_status",
    "my_status", "my_status_set_by", "my_note", "classification", "confidence", "classifier_reasons",
    "assignment_raw_id", "is_hidden", "title_source", "kind_source", "upstream_due_at", "due_changed_at",
    "upstream_updated_at",
]


def now() -> datetime:
    return datetime.now(UTC)


def client() -> AsyncMongoClient[dict[str, Any]]:
    global _client
    if _client is None:
        uri = get_settings().mongodb_uri
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncMongoClient(uri, tz_aware=True, tzinfo=UTC, uuidRepresentation="standard",
                                   serverSelectionTimeoutMS=15_000, appname="EZTracker")
    return _client


def database() -> AsyncDatabase[dict[str, Any]]:
    return client()[get_settings().mongodb_db]


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def out(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mongo doc → API shape: `_id` becomes `id`, internal fields dropped."""
    if doc is None:
        return None
    d = {k: v for k, v in doc.items() if k not in ("_id", "user_id")}
    d["id"] = doc["_id"]
    return d


async def ensure_indexes() -> None:
    db = database()
    await db.users.create_index("email", unique=True)
    await db.courses.create_index([("user_id", ASCENDING), ("nexus_course_id", ASCENDING)], unique=True,
                                  partialFilterExpression={"nexus_course_id": {"$type": "string"}})
    await db.course_aliases.create_index([("user_id", ASCENDING), ("course_id", ASCENDING), ("alias", ASCENDING)],
                                         unique=True)
    await db.nexus_assignments_raw.create_index([("user_id", ASCENDING), ("nexus_assignment_id", ASCENDING)],
                                                unique=True)
    await db.nexus_notifications_raw.create_index([("user_id", ASCENDING), ("nexus_notification_id", ASCENDING)],
                                                  unique=True)
    await db.work_items.create_index([("user_id", ASCENDING), ("course_id", ASCENDING), ("due_at", ASCENDING)])
    await db.work_items.create_index([("user_id", ASCENDING), ("my_status", ASCENDING), ("due_at", ASCENDING)])
    await db.work_items.create_index([("title", "text"), ("instructions_md", "text")], name="work_items_text",
                                     weights={"title": 5, "instructions_md": 1})
    await db.work_item_sources.create_index([("work_item_id", ASCENDING), ("notification_id", ASCENDING)],
                                            unique=True)
    await db.work_item_sources.create_index("notification_id")
    await db.work_item_events.create_index([("work_item_id", ASCENDING), ("created_at", DESCENDING)])
    await db.work_item_events.create_index("undo_token", sparse=True)
    await db.sync_runs.create_index([("user_id", ASCENDING), ("started_at", DESCENDING)])
    await db.user_settings.create_index("calendar_token", unique=True)
    await db.locks.create_index("expires_at", expireAfterSeconds=0)


# --------------------------------------------------------------------------- users & auth

async def create_user(email: str, password_hash: str) -> str:
    uid = str(uuid.uuid4())
    await database().users.insert_one({"_id": uid, "email": email.lower().strip(), "password_hash": password_hash,
                                       "created_at": now()})
    await database().user_settings.insert_one({"_id": uid, "calendar_token": secrets.token_hex(24),
                                               "created_at": now()})
    return uid


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    return await database().users.find_one({"email": email.lower().strip()})


async def get_user(uid: str) -> dict[str, Any] | None:
    return await database().users.find_one({"_id": uid})


async def set_password(uid: str, password_hash: str) -> None:
    await database().users.update_one({"_id": uid}, {"$set": {"password_hash": password_hash,
                                                              "password_changed_at": now()}})


async def count_users() -> int:
    return await database().users.count_documents({})


# --------------------------------------------------------------------------- state load / apply

def _wi(doc: dict[str, Any]) -> WorkItem:
    fields = {k: doc[k] for k in WORK_ITEM_FIELDS if k in doc}
    fields["links"] = doc.get("links") or []
    fields["classifier_reasons"] = doc.get("classifier_reasons") or []
    return WorkItem(id=doc["_id"], **fields)


async def load_state(user_id: str, item_ids: list[str] | None = None) -> State:
    db = database()
    s = State()
    async for r in db.courses.find({"user_id": user_id}):
        s.courses[r["_id"]] = Course(
            id=r["_id"], name=r["name"], nexus_course_id=r.get("nexus_course_id"), short_name=r.get("short_name"),
            instructor=r.get("instructor"), category=r.get("category") or "other", mode=r.get("mode"),
            term=r.get("term"), color_index=r.get("color_index", 0), is_archived=r.get("is_archived", False))
    async for r in db.course_aliases.find({"user_id": user_id}):
        s.aliases[r["_id"]] = Alias(r["_id"], r["course_id"], r["alias"], r.get("source", "seed"),
                                    r.get("weight", 1.0))
    if item_ids is None:
        async for r in db.nexus_assignments_raw.find({"user_id": user_id}):
            s.assignments[r["_id"]] = AssignmentRow(
                id=r["_id"], nexus_assignment_id=r["nexus_assignment_id"], title=r["title"],
                content_hash=r["content_hash"], course_name_raw=r.get("course_name_raw"), type_raw=r.get("type_raw"),
                due_at=r.get("due_at"), status_raw=r.get("status_raw"), description_html=r.get("description_html"),
                attachments=r.get("attachments") or [], url=r.get("url"), payload=r.get("payload") or {})
        async for r in db.nexus_notifications_raw.find({"user_id": user_id}):
            s.notifications[r["_id"]] = NotificationRow(
                id=r["_id"], nexus_notification_id=r["nexus_notification_id"], content_hash=r["content_hash"],
                title=r.get("title"), category_raw=r.get("category_raw"), snippet=r.get("snippet"),
                body_html=r.get("body_html"), published_at=r.get("published_at"),
                is_unread_on_nexus=r.get("is_unread_on_nexus"), link_url=r.get("link_url"),
                payload=r.get("payload") or {})
        items = [d async for d in db.work_items.find({"user_id": user_id})]
    else:
        items = [d async for d in db.work_items.find({"user_id": user_id, "_id": {"$in": item_ids}})]
    for d in items:
        s.work_items[d["_id"]] = _wi(d)
    ids = list(s.work_items)
    async for r in db.work_item_sources.find({"work_item_id": {"$in": ids}}):
        s.sources.add((r["work_item_id"], r["notification_id"]))
    return s


def _wi_doc(user_id: str, wi: WorkItem) -> dict[str, Any]:
    d = asdict(wi)
    return {"_id": d.pop("id"), "user_id": user_id, **d}


async def apply_changes(user_id: str, cs: ChangeSet) -> None:
    """Apply a ChangeSet atomically (one transaction). Order respects references."""
    db = database()
    t = now()
    async with client().start_session() as session:
        async with await session.start_transaction():
            for c in cs.courses_upsert.values():
                fields = {k: getattr(c, k) for k in ("nexus_course_id", "name", "instructor", "category", "mode",
                                                     "term")}
                await db.courses.update_one(
                    {"_id": c.id, "user_id": user_id},
                    {"$set": {**fields, "updated_at": t},
                     "$setOnInsert": {"short_name": c.short_name, "color_index": c.color_index,
                                      "is_archived": c.is_archived, "created_at": t}},
                    upsert=True, session=session)
            if cs.aliases_delete:
                await db.course_aliases.delete_many({"_id": {"$in": list(cs.aliases_delete)}, "user_id": user_id},
                                                    session=session)
            for a in cs.aliases_insert.values():
                await db.course_aliases.update_one(
                    {"user_id": user_id, "course_id": a.course_id, "alias": a.alias},
                    {"$set": {"weight": a.weight, "source": a.source},
                     "$setOnInsert": {"_id": a.id, "created_at": t}}, upsert=True, session=session)
            for a in cs.aliases_update.values():
                await db.course_aliases.update_one({"_id": a.id, "user_id": user_id}, {"$set": {"weight": a.weight}},
                                                   session=session)
            for r in cs.assignments_upsert.values():
                d = asdict(r)
                rid = d.pop("id")
                await db.nexus_assignments_raw.update_one(
                    {"user_id": user_id, "nexus_assignment_id": r.nexus_assignment_id},
                    {"$set": {**d, "last_seen_at": t}, "$setOnInsert": {"_id": rid, "first_seen_at": t}},
                    upsert=True, session=session)
            if cs.assignments_touch:
                await db.nexus_assignments_raw.update_many({"_id": {"$in": list(cs.assignments_touch)}},
                                                           {"$set": {"last_seen_at": t}}, session=session)
            for n in cs.notifications_upsert.values():
                d = asdict(n)
                nid = d.pop("id")
                await db.nexus_notifications_raw.update_one(
                    {"user_id": user_id, "nexus_notification_id": n.nexus_notification_id},
                    {"$set": {**d, "last_seen_at": t}, "$setOnInsert": {"_id": nid, "first_seen_at": t}},
                    upsert=True, session=session)
            if cs.notifications_touch:
                await db.nexus_notifications_raw.update_many({"_id": {"$in": list(cs.notifications_touch)}},
                                                             {"$set": {"last_seen_at": t}}, session=session)
            for wi in cs.work_items_insert.values():
                await db.work_items.insert_one({**_wi_doc(user_id, wi), "first_seen_at": t, "updated_at": t},
                                               session=session)
            for wid, fields in cs.work_items_update.items():
                if wid in cs.work_items_insert or not fields:
                    continue
                sets = {k: v for k, v in fields.items() if k in WORK_ITEM_FIELDS}
                await db.work_items.update_one({"_id": wid, "user_id": user_id}, {"$set": {**sets, "updated_at": t}},
                                               session=session)
            for (w, nid) in cs.sources_delete:
                await db.work_item_sources.delete_one({"work_item_id": w, "notification_id": nid}, session=session)
            for (w, nid) in cs.sources_insert:
                await db.work_item_sources.update_one({"work_item_id": w, "notification_id": nid},
                                                      {"$setOnInsert": {"_id": str(uuid.uuid4()), "user_id": user_id}},
                                                      upsert=True, session=session)
            events = [{"_id": str(uuid.uuid4()), "user_id": user_id, "work_item_id": e.work_item_id, "actor": e.actor,
                       "event": e.event, "from_value": e.from_value, "to_value": e.to_value,
                       "undo_token": e.undo_token, "created_at": t}
                      for e in cs.events if e.work_item_id not in cs.work_items_delete]
            if events:
                await db.work_item_events.insert_many(events, session=session)
            if cs.work_items_delete:
                ids = list(cs.work_items_delete)
                await db.work_items.delete_many({"_id": {"$in": ids}, "user_id": user_id}, session=session)
                await db.work_item_events.delete_many({"work_item_id": {"$in": ids}}, session=session)
                await db.work_item_sources.delete_many({"work_item_id": {"$in": ids}}, session=session)


# --------------------------------------------------------------------------- reads for the API

async def list_courses(user_id: str) -> list[dict[str, Any]]:
    return [out(d) async for d in database().courses.find({"user_id": user_id}).sort("name", 1)]  # type: ignore[misc]


async def list_items(user_id: str) -> list[dict[str, Any]]:
    return [out(d) async for d in database().work_items.find({"user_id": user_id})]  # type: ignore[misc]


async def get_item(user_id: str, item_id: str) -> dict[str, Any] | None:
    return out(await database().work_items.find_one({"_id": item_id, "user_id": user_id}))


async def item_detail(user_id: str, item_id: str) -> dict[str, Any] | None:
    db = database()
    if not await db.work_items.find_one({"_id": item_id, "user_id": user_id}, {"_id": 1}):
        return None
    nids = [r["notification_id"] async for r in db.work_item_sources.find({"work_item_id": item_id})]
    sources = [{"id": n["_id"], **{k: n.get(k) for k in ("title", "snippet", "category_raw", "published_at",
                                                        "link_url")}}
               async for n in db.nexus_notifications_raw.find({"_id": {"$in": nids}, "user_id": user_id})]
    events = [{"id": e["_id"], **{k: e.get(k) for k in ("actor", "event", "from_value", "to_value", "created_at")}}
              async for e in db.work_item_events.find({"work_item_id": item_id, "user_id": user_id})
              .sort("created_at", -1).limit(50)]
    return {"sources": sorted(sources, key=lambda s: s.get("published_at") or now(), reverse=True), "events": events}


async def search_items(user_id: str, q: str, limit: int = 20) -> list[dict[str, Any]]:
    cur = database().work_items.find({"user_id": user_id, "$text": {"$search": q}},
                                     {"score": {"$meta": "textScore"}}).sort([("score", {"$meta": "textScore"})])
    found = [out({k: v for k, v in d.items() if k != "score"}) async for d in cur.limit(limit)]
    if found:
        return found  # type: ignore[return-value]
    # prefix fallback so "lensk" finds "Lenskart" as you type
    import re as _re
    rx = {"$regex": _re.escape(q.strip()), "$options": "i"}
    return [out(d) async for d in database().work_items.find(  # type: ignore[misc]
        {"user_id": user_id, "$or": [{"title": rx}, {"instructions_md": rx}]}).limit(limit)]


async def events_for_undo(user_id: str, token: str, window_s: int) -> list[dict[str, Any]]:
    since = now() - timedelta(seconds=window_s)
    cur = database().work_item_events.find({"user_id": user_id, "undo_token": token, "actor": "user",
                                            "created_at": {"$gt": since}}).sort("created_at", -1)
    return [dict(d) async for d in cur]


async def burn_undo_token(user_id: str, token: str) -> None:
    await database().work_item_events.update_many({"user_id": user_id, "undo_token": token},
                                                  {"$set": {"undo_token": None}})


async def patch_course(user_id: str, course_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    doc = await database().courses.find_one_and_update(
        {"_id": course_id, "user_id": user_id}, {"$set": {**fields, "updated_at": now()}},
        return_document=ReturnDocument.AFTER)
    return out(doc)


async def course_exists(user_id: str, course_id: str) -> bool:
    return await database().courses.count_documents({"_id": course_id, "user_id": user_id}, limit=1) > 0


async def list_aliases(user_id: str, course_id: str) -> list[dict[str, Any]]:
    cur = database().course_aliases.find({"user_id": user_id, "course_id": course_id}).sort([("source", 1),
                                                                                            ("alias", 1)])
    return [out(d) async for d in cur]  # type: ignore[misc]


async def add_alias(user_id: str, course_id: str, alias: str) -> dict[str, Any]:
    doc = await database().course_aliases.find_one_and_update(
        {"user_id": user_id, "course_id": course_id, "alias": alias},
        {"$set": {"source": "user", "weight": 1.0}, "$setOnInsert": {"_id": str(uuid.uuid4()), "created_at": now()}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return out(doc)  # type: ignore[return-value]


async def delete_alias(user_id: str, course_id: str, alias_id: str) -> None:
    await database().course_aliases.delete_one({"_id": alias_id, "course_id": course_id, "user_id": user_id})


async def export_items(user_id: str) -> list[dict[str, Any]]:
    names = {c["_id"]: c["name"] async for c in database().courses.find({"user_id": user_id}, {"name": 1})}
    rows = []
    async for d in database().work_items.find({"user_id": user_id}).sort("due_at", 1):
        rows.append({**out(d), "course": names.get(d.get("course_id"))})  # type: ignore[dict-item]
    return rows


async def calendar_token(user_id: str, rotate: bool = False) -> str:
    db = database()
    if rotate:
        tok = secrets.token_hex(24)
        await db.user_settings.update_one({"_id": user_id}, {"$set": {"calendar_token": tok}}, upsert=True)
        return tok
    doc = await db.user_settings.find_one({"_id": user_id})
    if doc and doc.get("calendar_token"):
        return str(doc["calendar_token"])
    return await calendar_token(user_id, rotate=True)


async def user_for_calendar_token(token: str) -> str | None:
    doc = await database().user_settings.find_one({"calendar_token": token})
    return doc["_id"] if doc else None


async def calendar_items(user_id: str) -> list[dict[str, Any]]:
    names = {c["_id"]: c.get("short_name") async for c in database().courses.find({"user_id": user_id})}
    cur = database().work_items.find({"user_id": user_id, "due_at": {"$ne": None}, "is_hidden": False,
                                      "my_status": {"$in": ["pending", "in_progress"]}})
    return [{"id": d["_id"], "title": d["title"], "due_at": d["due_at"], "links": d.get("links") or [],
             "short_name": names.get(d.get("course_id"))} async for d in cur]


# --------------------------------------------------------------------------- sync runs, lock, credentials

async def try_lock(user_id: str, ttl_s: int = 900) -> bool:
    """A lock document; it expires on its own (TTL index) if a run dies without releasing it."""
    t = now()
    try:
        await database().locks.insert_one({"_id": f"sync:{user_id}", "acquired_at": t,
                                           "expires_at": t + timedelta(seconds=ttl_s)})
        return True
    except DuplicateKeyError:
        stale = await database().locks.find_one_and_update(
            {"_id": f"sync:{user_id}", "expires_at": {"$lt": t}},
            {"$set": {"acquired_at": t, "expires_at": t + timedelta(seconds=ttl_s)}})
        return stale is not None


async def unlock(user_id: str) -> None:
    await database().locks.delete_one({"_id": f"sync:{user_id}"})


async def create_run(user_id: str, trigger: str) -> str:
    rid = str(uuid.uuid4())
    await database().sync_runs.insert_one({"_id": rid, "user_id": user_id, "trigger": trigger, "status": "running",
                                           "started_at": now(), "finished_at": None, "stats": {},
                                           "surface_errors": []})
    return rid


async def update_run_stats(run_id: str, stats: dict[str, Any]) -> None:
    await database().sync_runs.update_one({"_id": run_id}, {"$set": {f"stats.{k}": v for k, v in stats.items()}})


async def finish_run(run_id: str, status: str, stats: dict[str, Any], surface_errors: list[dict[str, Any]],
                     log_excerpt: str | None = None) -> None:
    await database().sync_runs.update_one({"_id": run_id}, {"$set": {
        "status": status, "finished_at": now(), "stats": stats, "surface_errors": surface_errors,
        "log_excerpt": log_excerpt}})


async def latest_run(user_id: str) -> dict[str, Any] | None:
    return out(await database().sync_runs.find_one({"user_id": user_id}, sort=[("started_at", -1)]))


async def recent_runs(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    cur = database().sync_runs.find({"user_id": user_id}).sort("started_at", -1).limit(limit)
    return [out(d) async for d in cur]  # type: ignore[misc]


async def last_success_at(user_id: str | None = None) -> datetime | None:
    q: dict[str, Any] = {"status": {"$in": ["success", "partial"]}}
    if user_id:
        q["user_id"] = user_id
    doc = await database().sync_runs.find_one(q, sort=[("finished_at", -1)])
    return doc["finished_at"] if doc else None


async def last_full_backfill(user_id: str) -> datetime | None:
    doc = await database().sync_runs.find_one({"user_id": user_id, "stats.full_backfill": True},
                                              sort=[("started_at", -1)])
    return doc["started_at"] if doc else None


async def known_ids(user_id: str) -> tuple[set[str], set[str]]:
    db = database()
    notifs = {d["nexus_notification_id"] async for d in db.nexus_notifications_raw.find(
        {"user_id": user_id}, {"nexus_notification_id": 1})}
    detailed = {d["nexus_assignment_id"] async for d in db.nexus_assignments_raw.find(
        {"user_id": user_id, "description_html": {"$ne": None}}, {"nexus_assignment_id": 1})}
    return notifs, detailed


async def get_credentials(user_id: str) -> dict[str, Any] | None:
    return await database().nexus_credentials.find_one({"_id": user_id})


async def save_credentials(user_id: str, email: str, password_cipher: bytes, state_cipher: bytes | None) -> None:
    await database().nexus_credentials.update_one(
        {"_id": user_id},
        {"$set": {"nexus_email": email, "password_ciphertext": password_cipher, "storage_state_cipher": state_cipher,
                  "last_login_at": now(), "last_error": None, "updated_at": now()}}, upsert=True)


async def save_storage_state(user_id: str, state_cipher: bytes) -> None:
    await database().nexus_credentials.update_one(
        {"_id": user_id}, {"$set": {"storage_state_cipher": state_cipher, "last_login_at": now(), "last_error": None}})


async def set_credentials_error(user_id: str, message: str) -> None:
    await database().nexus_credentials.update_one({"_id": user_id}, {"$set": {"last_error": message}})


async def delete_credentials(user_id: str) -> None:
    await database().nexus_credentials.delete_one({"_id": user_id})


async def connection_status(user_id: str) -> dict[str, Any]:
    r = await database().nexus_credentials.find_one({"_id": user_id}, {"password_ciphertext": 0,
                                                                        "storage_state_cipher": 0})
    if r is None:
        return {"connected": False, "last_login_at": None, "last_error": None}
    return {"connected": True, "nexus_email": r.get("nexus_email"), "last_login_at": r.get("last_login_at"),
            "last_error": r.get("last_error")}


async def all_connected_users() -> list[str]:
    return [d["_id"] async for d in database().nexus_credentials.find({}, {"_id": 1})]
