"""Export the fixture pipeline result as JSON for the web app's offline demo backend.

    python -m eztracker.devdata_export > ../web/src/lib/demo-data.json

Produced by the real pipeline, so demo classifications are exactly what the backend would do.
"""

import copy
import json
import sys
from dataclasses import asdict
from datetime import datetime

from .devdata import ASSIGNMENTS, BASE, COURSES, NOTIFICATIONS, NOW
from .models import State
from .pipeline.merge import Fetched, run_pipeline


def main() -> None:
    s = State()
    fetched = Fetched(copy.deepcopy(COURSES), copy.deepcopy(ASSIGNMENTS), copy.deepcopy(NOTIFICATIONS))
    run_pipeline(s, fetched, NOW, BASE)

    def ser(v: object) -> object:
        return v.isoformat() if isinstance(v, datetime) else v

    out = {
        "generated_for": NOW.isoformat(),
        "courses": [asdict(c) for c in s.courses.values()],
        "aliases": [asdict(a) for a in s.aliases.values()],
        "work_items": [{**asdict(w), "first_seen_at": NOW.isoformat(), "updated_at": NOW.isoformat()}
                       for w in s.work_items.values()],
        "notifications": [{k: getattr(n, k) for k in ("id", "title", "snippet", "category_raw", "published_at",
                                                      "link_url")} for n in s.notifications.values()],
        "sources": [list(x) for x in sorted(s.sources)],
    }
    json.dump(out, sys.stdout, default=ser, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
