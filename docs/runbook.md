# EZTracker runbook

## First-time setup

1. **Supabase project:** create one at supabase.com.
   - SQL editor: run `supabase/migrations/0001_core.sql`, then `0002…`, then `0003…` in order. Or use
     `supabase db push` with the CLI.
   - Authentication → Providers → Email: enable magic link.
   - Authentication → Users → "Invite user" with your own email.
   - Authentication → Settings → **turn off "Allow new users to sign up"**. EZTracker is single-user (§12).
   - Authentication → URL configuration: add your web origin(s) to redirect URLs.
2. **`.env`:** `cp .env.example .env` and fill in the values from Settings → API and Settings → Database.
   - Use the **session pooler / direct** connection string (port 5432) for `DATABASE_URL`, so advisory locks hold
     for a whole run.
   - `make keygen` → `CREDENTIALS_ENCRYPTION_KEY`.
3. `make install`, then `make api` and `make web` (or `docker compose up`).
4. Open the web app, sign in by magic link, then connect Nexus on the onboarding card.

## First-time discovery (Phase 1)

Discovery walks Nexus with **your** account and records its JSON API, so it must be run by you, locally:

```bash
make connect          # visible browser: sign in yourself; saves apps/api/.discovery/storage_state.json
make discover         # headless walk → docs/nexus_api_map.md (redacted); raw captures stay git-ignored
```

Password-form login alternative: set `NEXUS_EMAIL`/`NEXUS_PASSWORD` in `.env` and skip `make connect`.
Then review `docs/nexus_api_map.md`, copy the suggested pins into
`apps/api/eztracker/scraper/endpoints.json`, and commit both files. Check the map for anything personal first.

## Nexus uses Google sign-in / OTP

Automated login stops with "Nexus requires additional verification" and does not retry. Connect once with a
visible browser. The session is stored encrypted:

```bash
make connect USER_ID=<your auth.users id> EMAIL=<nexus email>
```

When that session expires, the sync fails with "Your Nexus session expired — reconnect Nexus". Run it again.

## Reconnect Nexus (password changed)

Settings → Nexus connection → **Reconnect**. It verifies the new login with Nexus before replacing the stored one.
**Disconnect** deletes the encrypted password and session. Items stay.

## Rotate the encryption key

Stored ciphertexts can't be decrypted with a new key, so:

1. `make keygen` → set the new `CREDENTIALS_ENCRYPTION_KEY` and redeploy the API.
2. `delete from nexus_credentials;` (or Settings → Disconnect).
3. Reconnect Nexus in the app.

## Fix a broken adapter (Nexus changed its UI or API)

1. Settings → Sync shows `surface_errors`. `strategy: dom` with level `warning` means JSON failed and the DOM
   fallback worked. Level `error` means both failed and the run is `partial`. Other surfaces still sync.
2. `make discover` to re-record the API and diff `docs/nexus_api_map.md`.
3. Update the pins in `endpoints.json`, or the key lists in `scraper/adapters/base.py::KEYS`, or the DOM parsers
   in `dom_strategy.py`.
4. Add the new response shape as a fixture in `tests/test_scraper_parsers.py` (redacted), then `make test`.
5. Settings → Sync now (once per 10 min) to verify.

## Stale data banner

It appears when there has been no successful run for more than 7 hours. Check `/api/health` (`scheduler: true`,
`db: true`), the host's logs, and the latest `sync_runs.surface_errors`. The scheduler also runs once at startup
if the last success is older than 3 hours.

## Backups and export

- Supabase takes daily backups (Project → Database → Backups). To restore, pick a point and restore, then
  redeploy the API. It holds no state.
- Owner export: Settings → Data export (JSON / CSV), or `GET /api/export?format=csv`.
- Full SQL dump: `pg_dump "$DATABASE_URL" -n public > eztracker-$(date +%F).sql`.

## Deploy

- **API** (Railway / Render / Fly): build `apps/api/Dockerfile`. Set all backend env vars. `PORT` is honoured.
  Run exactly **one** instance. The advisory lock guards against doubles anyway. Health check: `/api/health`.
- **Web** (Vercel / Netlify): root `apps/web`, build `npm run build`, output `dist`. Set `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY` and `VITE_API_URL`. `vercel.json` handles SPA rewrites. Set the API's
  `FRONTEND_ORIGIN` to this URL (CORS).
- **GitHub Actions alternative runner:** a scheduled workflow can `python -c "import asyncio; from eztracker.sync
  import run_sync; asyncio.run(run_sync('<uid>','schedule'))"` every 3 h with the backend secrets. Set
  `SCHEDULER_ENABLED=false` on the API if you do this.

## Local database tests

```bash
./scripts/db_test.sh --seed   # throwaway Postgres: migrations, seed, RLS assertions, DB + API integration tests
./scripts/gen_seed_sql.sh     # regenerate supabase/seed.sql from the Python fixtures
```
