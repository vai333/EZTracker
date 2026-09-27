"""Owner account management — run locally against your Atlas cluster.

    make create-user EMAIL=you@example.com     # prompts for a password (not echoed)
    make reset-password EMAIL=you@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from . import db
from .auth import hash_password


def _ask() -> str:
    pw = getpass.getpass("New EZTracker password (min 10 chars): ")
    if len(pw) < 10:
        sys.exit("Password must be at least 10 characters.")
    if getpass.getpass("Repeat: ") != pw:
        sys.exit("Passwords did not match.")
    return pw


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["create", "reset"])
    ap.add_argument("--email", required=True)
    a = ap.parse_args()
    await db.ensure_indexes()
    existing = await db.get_user_by_email(a.email)
    if a.action == "create":
        if existing:
            sys.exit("That user already exists — use reset.")
        if await db.count_users() > 0:
            sys.exit("EZTracker is single-owner and an account already exists.")
        uid = await db.create_user(a.email, hash_password(_ask()))
        print(f"Created owner {a.email} (id {uid}).")
    else:
        if not existing:
            sys.exit("No such user.")
        await db.set_password(existing["_id"], hash_password(_ask()))
        print("Password updated.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
