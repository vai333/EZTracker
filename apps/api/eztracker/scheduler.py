"""APScheduler: every 3h ± 5 min jitter, one instance, coalesced; advisory lock guards double runs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import db
from .config import get_settings
from .logs import log
from .sync import SyncBusy, run_sync

JOB_ID = "eztracker_sync"
scheduler = AsyncIOScheduler(timezone="UTC")


async def scheduled_sync() -> None:
    for uid in await db.all_connected_users():
        try:
            await run_sync(uid, "schedule")
        except SyncBusy:
            log.info("scheduled_sync_skipped_busy", user_id=uid)
        except Exception:  # noqa: BLE001
            log.exception("scheduled_sync_error", user_id=uid)


async def start() -> None:
    s = get_settings()
    scheduler.add_job(scheduled_sync, IntervalTrigger(hours=s.sync_interval_hours, jitter=300), id=JOB_ID,
                      max_instances=1, coalesce=True, replace_existing=True)
    scheduler.start()
    # on startup, run once if the last success is older than the interval
    try:
        last = await db.last_success_at()
        if last is None or last < datetime.now(UTC) - timedelta(hours=s.sync_interval_hours):
            scheduler.add_job(scheduled_sync, id=JOB_ID + "_startup", replace_existing=True)
    except Exception:  # noqa: BLE001
        log.exception("scheduler_startup_check_failed")


def next_run_time() -> datetime | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    return job.next_run_time if job else None


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
