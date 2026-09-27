# EZTracker

A personal academic command center for **Mesa Nexus**. It reads your Courses, My Work and Notifications every
3 hours, merges them into one list organised **by course**, and answers three questions in under five seconds:
*what's pending, when is it due, and what exactly do I have to do (and where is it)?*

- **Today** (Agenda): Overdue · Today · Tomorrow · This week · Later · No due date.
- **Board**: one column per course, with **Needs Review** pinned first. Drag a card, press **M** for *Move to…*,
  or press Space then ←/→ then Space. Every correction is sticky, can be undone (⌘Z), and teaches the classifier.
- **Detail drawer**: instructions, every source notification, change history, your note, and **Open in Nexus**.
- ⌘K search, a `.ics` calendar feed, light ("Ivory & Forest") and dark ("Obsidian & Champagne") themes, and
  it works on a phone.

## Try it now, without any setup

```bash
cd apps/web && npm install && npm run dev
```

With no Supabase configured, the web app runs on **demo data**. That data is produced by the real Python
pipeline from Nexus-shaped fixtures, and your changes persist in the browser. Append `?demo` to force demo mode.

## Architecture

```
React (Vite, TS) ──reads (RLS)──▶ Supabase Postgres + Auth + Realtime ◀──service role── FastAPI (Python)
      └──────── writes of intent (JWT) ────────────────────────────────────────────────▶ ├ APScheduler, every 3h
                                                                                          ├ Playwright scraper
                                                                                          └ merge + classify engine
```

| Path | What |
|---|---|
| `apps/api/eztracker/pipeline/` | normalize → classify → merge/diff with the **sticky rules** (pure functions, `State → ChangeSet`) |
| `apps/api/eztracker/scraper/` | session (encrypted `storage_state`), JSON-capture + DOM adapters, discovery, `connect` |
| `apps/api/eztracker/routes/` | §8 API: items / undo / merge, sync, credentials, courses & aliases, `.ics`, export |
| `apps/web/src/features/` | board, agenda, item drawer, ⌘K, onboarding, settings, courses, `/styleguide` |
| `supabase/migrations/` | schema, RLS (read-only client; no client access to credentials), realtime |
| `docs/` | `decisions.md` (tree-of-thought notes), `runbook.md`, `nexus_api_map.md` |

## Setup (live)

See **[docs/runbook.md](docs/runbook.md)** for the full steps. Short version:

```bash
cp .env.example .env      # fill in the Supabase values; `make keygen` for CREDENTIALS_ENCRYPTION_KEY
make install
make api                  # :8000
make web                  # :5173
```

Apply `supabase/migrations/*.sql` to your project, invite yourself, and **disable public sign-ups**.

## Tests

```bash
make test                   # 79 backend unit tests + web unit tests
./scripts/db_test.sh --seed # throwaway Postgres: migrations, seed, RLS, DB + API integration tests
make e2e                    # Playwright: drag → reload persists, undo, keyboard move, 375px, …
make lint contrast          # ruff, mypy --strict, eslint, tsc, WCAG AA token gate
```

## Security notes

- Your Nexus password is Fernet-encrypted with a key that exists only in the API environment. It is decrypted
  only when the stored session has expired, never logged, and never sent to the browser. The browser can only
  read `connected / last_login_at / last_error` (view `nexus_connection_status`).
- The scraper is read-only and polite: one session, sequential requests, 0.4–1.2 s jitter, a 5-minute budget, a
  run every 3 h, and manual sync at most once per 10 min. CAPTCHA, MFA and SSO are surfaced, never bypassed.
- Your manual actions are never overwritten by scraped data. A property test runs arbitrary scraper input
  against pinned manual fields.
