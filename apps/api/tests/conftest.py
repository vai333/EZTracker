import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fixtures import ASSIGNMENTS, BASE, COURSES, NOTIFICATIONS, NOW  # noqa: E402

from eztracker.models import State  # noqa: E402
from eztracker.pipeline.merge import Fetched, run_pipeline  # noqa: E402


def fetched() -> Fetched:
    return Fetched(copy.deepcopy(COURSES), copy.deepcopy(ASSIGNMENTS), copy.deepcopy(NOTIFICATIONS))


@pytest.fixture
def synced_state() -> State:
    s = State()
    run_pipeline(s, fetched(), NOW, BASE)
    return s


def by_title(state: State, prefix: str):  # type: ignore[no-untyped-def]
    return next(w for w in state.work_items.values() if w.title.startswith(prefix))


def course_named(state: State, short: str) -> str:
    return next(c.id for c in state.courses.values() if c.short_name == short)
