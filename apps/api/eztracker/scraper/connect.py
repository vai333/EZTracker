"""One-time interactive connect: a visible browser opens Nexus, YOU sign in, we keep the session state.

This is the path for SSO / MFA / CAPTCHA logins, which EZTracker deliberately never automates.

    make connect                          # saves apps/api/.discovery/storage_state.json (for discovery)
    make connect USER_ID=<supabase uid>   # also stores it encrypted in nexus_credentials for syncing
"""

from __future__ import annotations

import argparse
import asyncio
import json

from playwright.async_api import async_playwright

from .. import crypto, db
from ..config import get_settings
from .discovery import RAW_DIR, STATE_FILE
from .session import AUTHED_PATH, LOGIN_HINTS


async def connect(user_id: str | None, email: str | None) -> None:
    base = get_settings().nexus_base_url.rstrip("/")
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=False)
        ctx = await b.new_context(locale="en-IN", timezone_id="Asia/Kolkata")
        page = await ctx.new_page()
        await page.goto(base + AUTHED_PATH + "/courses")
        print("Sign in to Nexus in the browser window. Waiting up to 5 minutes…", flush=True)
        # Logged in = on an LMS route, no login URL, no password box, and the app has rendered.
        # Require it twice in a row so a redirect mid-login doesn't count.
        stable = 0
        for _ in range(150):
            await asyncio.sleep(2)
            try:
                ok = (AUTHED_PATH in page.url and not LOGIN_HINTS.search(page.url)
                      and await page.locator("input[type=password]").count() == 0
                      and len((await page.locator("body").inner_text(timeout=3_000)).strip()) > 200)
            except Exception:  # noqa: BLE001 — page navigating
                ok = False
            stable = stable + 1 if ok else 0
            if stable >= 2:
                break
        else:
            await b.close()
            raise SystemExit("Timed out waiting for Nexus sign-in.")
        await page.wait_for_load_state("networkidle")
        print("Signed in — saving session.", flush=True)
        state = json.dumps(await ctx.storage_state())
        await b.close()
    RAW_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(state)
    print(f"Session saved to {STATE_FILE}")
    if user_id:
        await db.save_credentials(user_id, email or "sso", crypto.encrypt(""), crypto.encrypt(state))
        await db.close()
        print("Stored encrypted session for user", user_id)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id")
    ap.add_argument("--email")
    a = ap.parse_args()
    asyncio.run(connect(a.user_id, a.email))
