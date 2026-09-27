"""Load realistic fixture data for UI development.

    python -m eztracker.seed --user-id <supabase auth uid>

Due dates are shifted relative to *now* so the Agenda always has overdue / today / this-week items.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import UTC, datetime

from . import db
from .config import get_settings
from .devdata import ASSIGNMENTS, COURSES, NOTIFICATIONS, NOW
from .pipeline.merge import Fetched, run_pipeline


async def seed(user_id: str) -> None:
    shift = datetime.now(UTC) - NOW
    assignments = copy.deepcopy(ASSIGNMENTS)
    for a in assignments:
        a.due_at = a.due_at + shift if a.due_at else None
    notifications = copy.deepcopy(NOTIFICATIONS)
    for n in notifications:
        n.published_at = n.published_at + shift if n.published_at else None
    await db.ensure_indexes()
    state = await db.load_state(user_id)
    cs, stats = run_pipeline(state, Fetched(copy.deepcopy(COURSES), assignments, notifications),
                             datetime.now(UTC), get_settings().nexus_base_url)
    await db.apply_changes(user_id, cs)
    run_id = await db.create_run(user_id, "manual")
    await db.finish_run(run_id, "success", stats.as_dict(), [])
    print("seeded:", stats.as_dict())
    await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True)
    asyncio.run(seed(ap.parse_args().user_id))
