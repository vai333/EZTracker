"""Integration tests against real MongoDB (your Atlas cluster, a throwaway database that is dropped after).

Opt-in: `make test-integration` (sets EZ_TEST_MONGO=1 and reads MONGODB_URI from .env). Skipped otherwise.
Nexus is never contacted: the Playwright session and the sweep are replaced by fakes.
"""

import copy
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fixtures import ASSIGNMENTS, COURSES, NOTIFICATIONS

pytestmark = pytest.mark.skipif(os.environ.get("EZ_TEST_MONGO") != "1",
                                reason="set EZ_TEST_MONGO=1 (make test-integration) to run against MongoDB")


@pytest.fixture
async def env(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    from eztracker import config, crypto, db
    from eztracker.auth import hash_password

    dbname = f"eztracker_test_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("MONGODB_DB", dbname)
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("AUTH_JWT_SECRET", "t" * 40)
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    config.get_settings.cache_clear()
    await db.close()
    await db.ensure_indexes()
    uid = await db.create_user(f"{uuid.uuid4().hex[:6]}@test.local", hash_password("correct horse battery"))
    await db.save_credentials(uid, "me@nexus", crypto.encrypt("pw"), crypto.encrypt("{}"))
    yield uid
    await db.client().drop_database(dbname)
    await db.close()
    config.get_settings.cache_clear()


class FakeAdapter:
    def __init__(self, surface: str, records: Any, fail: bool = False) -> None:
        self.surface, self.records, self.fail = surface, records, fail

    async def fetch(self, session: Any, hints: Any):  # type: ignore[no-untyped-def]
        from eztracker.scraper.adapters.surfaces import SurfaceResult

        if self.fail:
            return SurfaceResult(self.surface, None, [{"surface": self.surface, "strategy": "dom",  # type: ignore[arg-type]
                                                        "level": "error", "message": "boom"}])
        return SurfaceResult(self.surface, copy.deepcopy(self.records), [])  # type: ignore[arg-type]


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class S:
        async def storage_state_json(self) -> str:
            return "{}"

    @asynccontextmanager
    async def fake_open(*a: Any, **k: Any):  # type: ignore[no-untyped-def]
        yield S()

    async def no_sweep(*a: Any, **k: Any):  # type: ignore[no-untyped-def]
        from eztracker.scraper.sweep import SweepResult

        return SweepResult()

    monkeypatch.setattr("eztracker.sync.open_session", fake_open)
    monkeypatch.setattr("eztracker.sync.run_sweep", no_sweep)


def adapters(fail: str | None = None) -> list[FakeAdapter]:
    return [FakeAdapter("courses", COURSES, fail == "courses"),
            FakeAdapter("assignments", ASSIGNMENTS, fail == "assignments"),
            FakeAdapter("notifications", NOTIFICATIONS, fail == "notifications")]


async def counts(uid: str) -> dict[str, int]:
    from eztracker import db

    d = db.database()
    return {name: await d[name].count_documents({"user_id": uid}) for name in (
        "courses", "course_aliases", "nexus_assignments_raw", "nexus_notifications_raw", "work_items",
        "work_item_sources", "work_item_events")}


async def test_two_syncs_second_is_zero_rows_and_events(env: str, fake_session: None) -> None:
    from eztracker import db
    from eztracker.sync import run_sync

    await run_sync(env, "manual", adapters())  # type: ignore[arg-type]
    first = await counts(env)
    assert first["work_items"] == 11 and first["work_item_events"] >= 11
    await run_sync(env, "manual", adapters())  # type: ignore[arg-type]
    assert await counts(env) == first
    statuses = [r["status"] for r in reversed(await db.recent_runs(env))]
    assert statuses == ["success", "success"]


async def test_surface_failure_is_partial(env: str, fake_session: None) -> None:
    from eztracker import db
    from eztracker.sync import run_sync

    await run_sync(env, "manual", adapters(fail="notifications"))  # type: ignore[arg-type]
    r = await db.latest_run(env)
    assert r and r["status"] == "partial" and r["surface_errors"][0]["surface"] == "notifications"
    assert (await counts(env))["nexus_assignments_raw"] == 5


async def test_move_is_manual_survives_sync_learns_and_undoes(env: str, fake_session: None) -> None:
    from eztracker import db
    from eztracker.pipeline import actions
    from eztracker.sync import run_sync

    await run_sync(env, "manual", adapters())  # type: ignore[arg-type]
    d = db.database()
    item = (await d.work_items.find_one({"user_id": env, "title": {"$regex": "^Growth"}}))["_id"]  # type: ignore[index]
    cms = (await d.courses.find_one({"user_id": env, "short_name": "CMS"}))["_id"]  # type: ignore[index]
    token = str(uuid.uuid4())
    await db.apply_changes(env, actions.move_item(await db.load_state(env, [item]), item, cms, token))
    await run_sync(env, "manual", adapters())  # type: ignore[arg-type]
    row = await d.work_items.find_one({"_id": item})
    assert row and (row["course_id"], row["classification"]) == (cms, "manual")
    learned = {a["alias"] async for a in d.course_aliases.find({"course_id": cms, "source": "learned"})}
    assert {"growth", "gtm"} <= learned
    events = await db.events_for_undo(env, token, 300)
    await db.apply_changes(env, actions.undo(await db.load_state(env, [item]), events, token))
    row = await d.work_items.find_one({"_id": item})
    assert row and row["course_id"] is None and row["classification"] == "unresolved"
    assert await d.course_aliases.count_documents({"course_id": cms, "source": "learned"}) == 0


async def test_lock_blocks_concurrent_run(env: str, fake_session: None) -> None:
    from eztracker import db
    from eztracker.sync import SyncBusy, run_sync

    assert await db.try_lock(env)
    try:
        with pytest.raises(SyncBusy):
            await run_sync(env, "manual", adapters())  # type: ignore[arg-type]
    finally:
        await db.unlock(env)
    assert await db.try_lock(env)
    await db.unlock(env)


async def test_credentials_never_exposed(env: str) -> None:
    from eztracker import db

    status = await db.connection_status(env)
    assert status["connected"] is True
    assert "password_ciphertext" not in status and "storage_state_cipher" not in status
