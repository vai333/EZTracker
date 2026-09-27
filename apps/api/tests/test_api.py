"""HTTP-level tests against MongoDB: login, auth, reads, mutations, undo, calendar, cooldown, isolation."""

import os
import time
import uuid

import httpx
import jwt
import pytest
from test_integration_db import adapters, env, fake_session  # noqa: F401 — fixtures

pytestmark = pytest.mark.skipif(os.environ.get("EZ_TEST_MONGO") != "1",
                                reason="set EZ_TEST_MONGO=1 (make test-integration) to run against MongoDB")


@pytest.fixture
async def client(env: str):  # type: ignore[no-untyped-def]  # noqa: F811
    from eztracker import db
    from eztracker.main import app

    user = await db.get_user(env)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/auth/login", json={"email": user["email"], "password": "correct horse battery"})  # type: ignore[index]
        assert r.status_code == 200, r.text
        c.headers["authorization"] = f"Bearer {r.json()['token']}"
        yield c


async def _seed(uid: str) -> None:
    from eztracker.sync import run_sync

    await run_sync(uid, "schedule", adapters())  # type: ignore[arg-type]


async def test_login_rejects_bad_password_and_unknown_email(client: httpx.AsyncClient, env: str) -> None:  # noqa: F811
    from eztracker import db

    user = await db.get_user(env)
    r = await client.post("/api/auth/login", json={"email": user["email"], "password": "nope"})  # type: ignore[index]
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    r = await client.post("/api/auth/login", json={"email": "ghost@x.y", "password": "nope"})
    assert r.status_code == 401 and "nope" not in r.text
    assert (await client.get("/api/auth/me")).json()["id"] == env


async def test_requires_valid_token(client: httpx.AsyncClient) -> None:
    for h in ("", "Bearer nonsense",
              "Bearer " + jwt.encode({"sub": "x", "aud": "eztracker", "exp": int(time.time()) + 60}, "w" * 40,
                                     "HS256")):
        r = await client.get("/api/items", headers={"authorization": h})
        assert r.status_code == 401


async def test_reads_and_flow(client: httpx.AsyncClient, env: str, fake_session: None) -> None:  # noqa: F811
    await _seed(env)
    courses = (await client.get("/api/courses")).json()
    items = (await client.get("/api/items")).json()
    assert len(courses) == 9 and len(items) == 11 and all("user_id" not in i for i in items)
    growth = next(i for i in items if i["title"].startswith("Growth"))
    cms = next(c for c in courses if c["short_name"] == "CMS")
    r = await client.patch(f"/api/items/{growth['id']}/move", json={"course_id": cms["id"]})
    assert r.status_code == 200 and r.json()["item"]["classification"] == "manual"
    token = r.json()["undo_token"]
    detail = (await client.get(f"/api/items/{growth['id']}/detail")).json()
    assert detail["sources"] and detail["events"][0]["event"] == "moved"
    r = await client.post("/api/items/undo", json={"undo_token": token})
    assert r.status_code == 200 and r.json()["items"][0]["course_id"] is None
    assert (await client.post("/api/items/undo", json={"undo_token": token})).status_code == 410
    r = await client.patch(f"/api/items/{growth['id']}", json={"my_note": "ask Siddarth", "is_hidden": True})
    assert r.json()["item"]["my_note"] == "ask Siddarth"
    found = (await client.get("/api/items/search", params={"q": "lenskart"})).json()
    assert any("Lenskart" in i["title"] for i in found)
    r = await client.patch(f"/api/items/{growth['id']}/status", json={"my_status": "bogus"})
    assert r.status_code == 422 and "bogus" not in r.text


async def test_create_aliases_calendar_export(client: httpx.AsyncClient, env: str, fake_session: None) -> None:  # noqa: F811
    await _seed(env)
    cms = next(c for c in (await client.get("/api/courses")).json() if c["short_name"] == "CMS")
    r = await client.post("/api/items", json={"title": "Read chapter 4", "course_id": cms["id"],
                                              "due_at": "2026-10-01T18:29:00Z"})
    assert r.status_code == 201 and r.json()["item"]["origin"] == "manual"
    r = await client.post(f"/api/courses/{cms['id']}/aliases", json={"alias": "Positioning"})
    assert r.status_code == 201 and r.json()["alias"] == "positioning"
    path = (await client.get("/api/settings/calendar")).json()["path"]
    ics = await client.get(path, headers={"authorization": ""})
    assert ics.status_code == 200 and "Read chapter 4" in ics.text
    assert (await client.get("/api/calendar.ics?token=" + "x" * 32)).status_code == 404
    csv = await client.get("/api/export?format=csv")
    assert csv.status_code == 200 and "Read chapter 4" in csv.text


async def test_other_users_data_is_invisible(client: httpx.AsyncClient, env: str, fake_session: None) -> None:  # noqa: F811
    from eztracker.auth import issue_token

    await _seed(env)
    item = (await client.get("/api/items")).json()[0]
    stranger = {"authorization": f"Bearer {issue_token(str(uuid.uuid4()), 'x@y.z')}"}
    assert (await client.get("/api/items", headers=stranger)).json() == []
    r = await client.patch(f"/api/items/{item['id']}/status", json={"my_status": "submitted"}, headers=stranger)
    assert r.status_code == 404


async def test_manual_sync_cooldown(client: httpx.AsyncClient, env: str, fake_session: None) -> None:  # noqa: F811
    await _seed(env)
    assert (await client.post("/api/sync")).status_code == 429
    s = (await client.get("/api/sync/status")).json()
    assert s["stale"] is False and s["latest"]["status"] == "success"
