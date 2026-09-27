"""One sync run end to end (§6): lock → session → fetch surfaces → sweep → pipeline → apply → finish."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from . import crypto, db
from .config import get_settings
from .logs import log
from .notifier import default_notifier
from .pipeline.merge import Fetched, run_pipeline
from .scraper.adapters.base import FetchHints
from .scraper.adapters.surfaces import SurfaceAdapter, default_adapters
from .scraper.session import NexusAuthError, open_session
from .scraper.sweep import run_sweep


class SyncBusy(RuntimeError):
    pass


async def _hints(user_id: str) -> dict[str, FetchHints]:
    notif_ids, detailed = await db.known_ids(user_id)
    last_full = await db.last_full_backfill(user_id)
    full = last_full is None or last_full < datetime.now(UTC) - timedelta(days=7)
    return {"courses": FetchHints(full_backfill=full),
            "assignments": FetchHints(detailed_ids=detailed, full_backfill=full),
            "notifications": FetchHints(known_ids=notif_ids, full_backfill=full)}


async def run_sync(user_id: str, trigger: str, adapters: list[SurfaceAdapter] | None = None,
                   run_id: str | None = None) -> str:
    settings = get_settings()
    if not await db.try_lock(user_id, ttl_s=settings.run_budget_seconds + 300):
        if run_id:
            await db.finish_run(run_id, "failed", {}, [
                {"surface": "run", "strategy": "-", "level": "error", "message": "another sync was running"}])
        raise SyncBusy("another sync is already running")
    run_id = run_id or await db.create_run(user_id, trigger)
    errors: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    status = "failed"
    try:
        cred = await db.get_credentials(user_id)
        if cred is None:
            raise NexusAuthError("Nexus is not connected")
        hints = await _hints(user_id)
        stats["full_backfill"] = hints["notifications"].full_backfill

        def password() -> str:
            pw = crypto.decrypt(cred["password_ciphertext"])
            if not pw:
                raise NexusAuthError("Your Nexus session expired — reconnect Nexus in Settings.")
            return pw

        async def save_state(state_json: str) -> None:
            await db.save_storage_state(user_id, crypto.encrypt(state_json))

        storage = crypto.decrypt(cred["storage_state_cipher"]) if cred.get("storage_state_cipher") else None
        results: dict[str, list[Any] | None] = {}
        async with asyncio.timeout(settings.run_budget_seconds):
            async with open_session(cred["nexus_email"], password, storage, save_state) as sess:
                for ad in adapters or default_adapters():  # sequential by design (politeness)
                    await db.update_run_stats(run_id, {"phase": ad.surface})  # live onboarding progress
                    res = await ad.fetch(sess, hints[ad.surface])
                    results[ad.surface] = res.records
                    errors.extend(res.errors)
                # completeness sweep: every course page, forms, calendar, coverage audit
                await db.update_run_stats(run_id, {"phase": "sweep"})
                sw = await run_sweep(sess, results.get("courses"), results.get("assignments"),
                                     results.get("notifications"))
                errors.extend(sw.errors)
                stats["coverage"] = sw.coverage
                if sw.courses:
                    results["courses"] = (results.get("courses") or []) + sw.courses
                if sw.assignments:
                    results["assignments"] = (results.get("assignments") or []) + sw.assignments
                if sw.notifications:
                    results["notifications"] = (results.get("notifications") or []) + sw.notifications
                await save_state(await sess.storage_state_json())

        await db.update_run_stats(run_id, {"phase": "sorting"})
        state = await db.load_state(user_id)
        cs, st = run_pipeline(state, Fetched(results.get("courses"), results.get("assignments"),
                                             results.get("notifications")),
                              datetime.now(UTC), settings.nexus_base_url)
        await db.apply_changes(user_id, cs)
        stats.update(st.as_dict())
        stats["phase"] = "done"
        failed_surfaces = [s for s, r in results.items() if r is None]
        # coverage warnings keep the run "success"; they're listed in Settings → Sync
        status = "partial" if failed_surfaces or any(e.get("level") == "error" for e in errors) else "success"
        if len(failed_surfaces) == 3:
            status = "failed"
        await default_notifier().sync_finished(user_id, stats)
    except NexusAuthError as e:
        errors.append({"surface": "session", "strategy": "login", "level": "error", "message": str(e)})
        await db.set_credentials_error(user_id, str(e))
    except TimeoutError:
        errors.append({"surface": "run", "strategy": "-", "level": "error",
                       "message": f"run exceeded {settings.run_budget_seconds}s budget"})
    except Exception as e:  # noqa: BLE001
        log.exception("sync_crashed", user_id=user_id)
        errors.append({"surface": "run", "strategy": "-", "level": "error", "message": str(e)[:300]})
    finally:
        await db.finish_run(run_id, status, stats, errors)
        await db.unlock(user_id)
    log.info("sync_finished", user_id=user_id, run_id=run_id, status=status,
             stats={k: v for k, v in stats.items() if k != "coverage"})
    return run_id
