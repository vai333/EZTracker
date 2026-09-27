"""Surface adapters: JSON first, DOM fallback, a failing surface never aborts the others (§5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from ...logs import log
from ..session import NexusSession
from .base import FetchHints, SchemaMismatch, Strategy, Surface
from .dom_strategy import DomAssignments, DomCourses, DomNotifications
from .json_strategy import JsonAssignments, JsonCourses, JsonNotifications


def _transient(e: BaseException) -> bool:
    """Retry only 5xx / timeouts — never auth or schema problems."""
    msg = str(e).lower()
    return "timeout" in msg or any(f" {c}" in msg for c in ("500", "502", "503", "504"))


@dataclass
class SurfaceResult:
    surface: Surface
    records: list[Any] | None
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SurfaceAdapter:
    surface: Surface
    strategies: list[Strategy]

    async def fetch(self, session: NexusSession, hints: FetchHints) -> SurfaceResult:
        errors: list[dict[str, str]] = []
        for strat in self.strategies:
            try:
                async for attempt in AsyncRetrying(stop=stop_after_attempt(3), reraise=True,
                                                   wait=wait_exponential(multiplier=1, min=1, max=8),
                                                   retry=retry_if_exception(_transient)):
                    with attempt:
                        records = await strat.fetch(session, hints)
                if strat.name != "json":
                    errors.append({"surface": self.surface, "strategy": strat.name, "level": "warning",
                                   "message": "JSON strategy failed; used DOM fallback"})
                log.info("surface_fetched", surface=self.surface, strategy=strat.name, count=len(records))
                return SurfaceResult(self.surface, records, errors)
            except SchemaMismatch as e:
                errors.append({"surface": self.surface, "strategy": strat.name, "level": "warning",
                               "message": str(e)})
            except Exception as e:  # noqa: BLE001 — isolate surface failures
                log.warning("surface_failed", surface=self.surface, strategy=strat.name, error=str(e)[:300])
                errors.append({"surface": self.surface, "strategy": strat.name, "level": "error",
                               "message": str(e)[:300]})
        return SurfaceResult(self.surface, None, errors)


def default_adapters() -> list[SurfaceAdapter]:
    return [
        SurfaceAdapter("courses", [JsonCourses(), DomCourses()]),
        SurfaceAdapter("assignments", [JsonAssignments(), DomAssignments()]),
        SurfaceAdapter("notifications", [JsonNotifications(), DomNotifications()]),
    ]
