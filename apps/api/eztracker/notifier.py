"""Notifier seam (§13). v1 ships a no-op; future: 8 AM IST digest, Telegram/WhatsApp, browser push."""

from typing import Any, Protocol


class Notifier(Protocol):
    async def sync_finished(self, user_id: str, stats: dict[str, Any]) -> None: ...

    async def due_soon(self, user_id: str, items: list[dict[str, Any]]) -> None: ...


class NoopNotifier:
    async def sync_finished(self, user_id: str, stats: dict[str, Any]) -> None:
        return None

    async def due_soon(self, user_id: str, items: list[dict[str, Any]]) -> None:
        return None


def default_notifier() -> Notifier:
    return NoopNotifier()
