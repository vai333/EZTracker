"""Nexus session lifecycle (§5): reuse encrypted storage_state, re-login only when it has expired.

We surface — never bypass — CAPTCHA / MFA / SSO walls. If Nexus signs in through an identity provider
we can't drive headlessly, the user connects once with `python -m eztracker.scraper.connect` (a visible
browser where they sign in themselves) and we keep only the resulting session state.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

from ..config import get_settings
from ..logs import log

LOGIN_HINTS = re.compile(r"/(login|signin|sign-in|auth)(/|$|\?)", re.I)
AUTHED_PATH = "/student/lms"
CAPTCHA_SELECTORS = "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile'], .g-recaptcha"
MFA_TEXT = re.compile(r"(verification code|one[-\s]?time password|\bOTP\b|two[-\s]?factor|2FA)", re.I)
SSO_HOSTS = re.compile(r"(accounts\.google\.com|login\.microsoftonline\.com|okta\.com|auth0\.com)", re.I)


class NexusAuthError(RuntimeError):
    """User-safe message; shown in the UI as nexus_credentials.last_error."""


class NexusVerificationRequired(NexusAuthError):
    pass


@dataclass
class CapturedResponse:
    url: str
    method: str
    status: int
    request_headers: dict[str, str]
    body: Any


@dataclass
class NexusSession:
    context: BrowserContext
    page: Page
    base_url: str
    captured: list[CapturedResponse] = field(default_factory=list)
    _capturing: bool = False

    async def polite_pause(self) -> None:
        lo, hi = get_settings().delay_ms
        await asyncio.sleep(random.uniform(lo, hi) / 1000)

    def url(self, path: str) -> str:
        return path if path.startswith("http") else self.base_url.rstrip("/") + path

    async def goto(self, path: str, wait: str = "networkidle") -> None:
        await self.polite_pause()
        await self.page.goto(self.url(path), wait_until=wait, timeout=45_000)  # type: ignore[arg-type]

    @asynccontextmanager
    async def capture(self) -> AsyncIterator[list[CapturedResponse]]:
        """Record every JSON response the SPA makes while the block runs."""
        bucket: list[CapturedResponse] = []
        pending: list[asyncio.Task[None]] = []

        async def on_response(resp: Response) -> None:
            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype or resp.request.resource_type not in ("xhr", "fetch"):
                return
            try:
                body = await resp.json()
            except Exception:  # noqa: BLE001 — non-JSON body despite header
                return
            bucket.append(CapturedResponse(resp.url, resp.request.method, resp.status,
                                           dict(resp.request.headers), body))

        def handler(resp: Response) -> None:
            pending.append(asyncio.ensure_future(on_response(resp)))

        self.page.on("response", handler)
        try:
            yield bucket
        finally:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self.page.remove_listener("response", handler)
            self.captured.extend(bucket)

    async def scroll_to_end(self, max_rounds: int = 25) -> None:
        """Scroll the page (and inner scroll containers) until no new content loads."""
        last = -1
        for _ in range(max_rounds):
            height = await self.page.evaluate(
                """() => {
                  const els = [document.scrollingElement, ...document.querySelectorAll('main, [class*=scroll]')];
                  let h = 0;
                  for (const e of els) { if (!e) continue; e.scrollTop = e.scrollHeight; h += e.scrollHeight; }
                  return h;
                }""")
            await self.polite_pause()
            if height == last:
                break
            last = height

    async def storage_state_json(self) -> str:
        return json.dumps(await self.context.storage_state())


async def _looks_logged_in(page: Page) -> bool:
    return AUTHED_PATH in page.url and not LOGIN_HINTS.search(page.url)


async def _check_walls(page: Page) -> None:
    if SSO_HOSTS.search(page.url):
        raise NexusVerificationRequired(
            "Nexus signs in through an external identity provider — connect with the one-time "
            "browser sign-in (`make connect`) instead of a password.")
    if await page.locator(CAPTCHA_SELECTORS).count() > 0:
        raise NexusVerificationRequired("Nexus requires additional verification")
    body = (await page.locator("body").inner_text(timeout=5_000)) if await page.locator("body").count() else ""
    if MFA_TEXT.search(body or ""):
        raise NexusVerificationRequired("Nexus requires additional verification")


async def perform_login(page: Page, base_url: str, email: str, password: str) -> None:
    """Fill the Nexus login form. Raises NexusAuthError with a user-safe message on failure."""
    await page.goto(base_url.rstrip("/") + AUTHED_PATH + "/courses", wait_until="networkidle", timeout=45_000)
    if await _looks_logged_in(page):
        return
    await _check_walls(page)
    email_box = page.locator(
        "input[type=email], input[name*=email i], input[id*=email i], input[autocomplete=username], "
        "input[name*=user i], input[placeholder*=mail i], input[placeholder*=student i]").first
    pwd_box = page.locator("input[type=password]").first
    if await email_box.count() == 0 or await pwd_box.count() == 0:
        # some SPAs show a landing page with a "Login" button first
        btn = page.get_by_role("button", name=re.compile(r"(log ?in|sign ?in)", re.I)).first
        if await btn.count():
            await btn.click()
            await page.wait_for_load_state("networkidle")
            await _check_walls(page)
    if await email_box.count() == 0 or await pwd_box.count() == 0:
        raise NexusAuthError("Could not find the Nexus login form — the login page may have changed.")
    await email_box.fill(email)
    await pwd_box.fill(password)
    submit = page.locator("button[type=submit], input[type=submit]").first
    if await submit.count() == 0:
        submit = page.get_by_role("button", name=re.compile(r"(log ?in|sign ?in|continue)", re.I)).first
    await submit.click()
    try:
        await page.wait_for_url(re.compile(re.escape(AUTHED_PATH)), timeout=30_000)
    except Exception:  # noqa: BLE001
        await _check_walls(page)
        raise NexusAuthError("Nexus rejected the login — update your password") from None
    await page.wait_for_load_state("networkidle")


@asynccontextmanager
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        try:
            yield b
        finally:
            await b.close()


@asynccontextmanager
async def open_session(email: str | None, password_provider: Any, storage_state: str | None,
                       on_new_state: Any = None) -> AsyncIterator[NexusSession]:
    """Yield an authenticated NexusSession.

    password_provider: zero-arg callable returning the plaintext password — called ONLY if the stored
    session has expired, so the password is decrypted as rarely as possible.
    on_new_state: async callback(storage_state_json) invoked after a fresh login.
    """
    base = get_settings().nexus_base_url
    async with browser() as b:
        state = json.loads(storage_state) if storage_state else None
        ctx = await b.new_context(storage_state=state, locale="en-IN", timezone_id="Asia/Kolkata")
        page = await ctx.new_page()
        sess = NexusSession(ctx, page, base)
        await page.goto(base.rstrip("/") + AUTHED_PATH + "/courses", wait_until="networkidle", timeout=45_000)
        if not await _looks_logged_in(page):
            if not email or password_provider is None:
                raise NexusAuthError("Your Nexus session expired — reconnect Nexus in Settings.")
            last: Exception | None = None
            for attempt in range(2):  # login fails twice → give up, no retry loop (§5.3)
                try:
                    await perform_login(page, base, email, password_provider())
                    last = None
                    break
                except NexusVerificationRequired:
                    raise
                except NexusAuthError as e:
                    last = e
                    log.warning("nexus_login_failed", attempt=attempt + 1)
            if last:
                raise last
            if on_new_state:
                await on_new_state(await sess.storage_state_json())
        try:
            yield sess
        finally:
            await ctx.close()
