# Decisions

Each decision not fixed by the spec is recorded with three branches, scored 1–5 on
**C**orrectness · **S**implicity · **M**aintainability · **D**elight, then pruned. "Backtrack" marks a branch
that failed in practice and was replaced by the next-best one.

---

### D-001 · Name and package
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Rename to EZTracker; Python package `eztracker`; one constant each side** | 5 | 5 | 5 | 4 |
| Keep "Ledger" internally, brand only in UI | 4 | 4 | 2 | 3 |
| Name from env var at runtime | 4 | 2 | 3 | 3 |

Owner asked for **EZTracker**. Rename points: `apps/api/eztracker/config.py::APP_NAME`, `apps/web/src/lib/brand.ts::APP_NAME`.

### D-002 · Python version locally
| Branch | C | S | M | D |
|---|---|---|---|---|
| **3.13 locally (only interpreter installed), 3.12 in Docker + CI** | 5 | 5 | 4 | 3 |
| Install 3.12 via Homebrew first | 5 | 3 | 4 | 3 |
| Target 3.13 everywhere | 4 | 5 | 3 | 3 |

`requires-python >=3.12`; nothing 3.13-specific is used.

### D-003 · Database access from the API
| Branch | C | S | M | D |
|---|---|---|---|---|
| **asyncpg straight to Postgres (service-role DSN)** | 5 | 4 | 4 | 4 |
| supabase-py over PostgREST | 3 | 4 | 3 | 3 |
| SQLAlchemy ORM | 4 | 2 | 4 | 3 |

The sync needs `pg_try_advisory_lock` held for the whole run and multi-table atomic writes. PostgREST can't hold a
session-scoped lock. Every query filters by `user_id` explicitly because the service role bypasses RLS.

### D-004 · Pipeline shape
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Functional core: `State` + raw → in-memory mutations + `ChangeSet`; the DB applies it in one transaction** | 5 | 4 | 5 | 4 |
| Imperative SQL per step | 4 | 3 | 2 | 3 |
| DB triggers / stored procedures | 3 | 2 | 2 | 3 |

This makes idempotence ("second sync → empty ChangeSet") and the sticky rules property-testable without a
database (`tests/test_pipeline.py`, hypothesis). The DB layer (`db.py`) stays thin.

### D-005 · Getting data out of the SPA (refines Round 3)
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Capture the SPA's own JSON while navigating; find the right array by key-signature scoring; pin via `endpoints.json` after discovery** | 4 | 4 | 5 | 4 |
| Hard-code guessed endpoint URLs now | 2 | 4 | 2 | 3 |
| DOM only | 3 | 4 | 2 | 3 |

This works before `docs/nexus_api_map.md` exists and needs no auth-header replay, since the SPA sends its own
token. DOM parsing stays as a per-surface fallback (§5). Parsers are pure functions with unit tests.
**Status: discovery has not been run against live Nexus yet.** It needs the owner's login (see runbook).

### D-006 · SSO / MFA / CAPTCHA
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Detect and stop; offer `make connect`: a visible browser where the owner signs in themselves; keep only `storage_state`** | 5 | 4 | 4 | 4 |
| Automate the identity provider's login | 1 | 2 | 1 | 2 |
| Ask the owner to paste cookies | 3 | 3 | 2 | 1 |

§5 says surface, never bypass. Password login stays the primary path when Nexus uses a plain form.

### D-007 · Schema extensions (migration `0002_extensions.sql`)
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Add provenance columns to `work_items`: `title_source`, `kind_source`, `upstream_due_at`, `due_changed_at`, `upstream_updated_at`; `search_tsv`; `work_item_events.undo_token`; `user_settings` (calendar token)** | 5 | 4 | 5 | 5 |
| Derive everything from `work_item_events` at read time | 4 | 2 | 3 | 3 |
| JSON `overrides` blob on `work_items` | 3 | 4 | 2 | 3 |

§8 requires "sets relevant `*_source='user'`" for title and kind overrides. The 72h "Deadline changed" chip and
"Nexus says X — use it?" need cheap reads.

### D-008 · Classifier details within the §7 weights
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Keep the §7 weights. Full-name hit uses stemmed-token containment (so "Strategy" matches "Strategies"). A course short name or acronym ("BYOB", "DDDM") counts as an explicit reference (+0.6). The course core name is seeded as its own alias. "assessment" joins the deliverable words.** | 5 | 4 | 4 | 4 |
| Raise the alias weight so single signals auto-file | 3 | 5 | 3 | 3 |
| Fuzzy `partial_ratio` for full names | 3 | 4 | 3 | 3 |

All seven required §7 examples pass, plus 20 more fixtures. Honest consequence: instructor plus one alias is
0.55, below 0.70, so "Pranjal's frameworks session…" goes to **Needs Review with the correct top suggestion**.
It is never auto-filed on thin evidence. Tests assert the suggestion.

### D-009 · `classifier_reasons` shape
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Top-2 candidates as objects `{course_id, course, score, reasons[]}`** | 5 | 4 | 5 | 5 |
| Flat strings as in the §4 comment | 3 | 5 | 3 | 2 |
| Separate `suggestions` column | 4 | 3 | 3 | 4 |

The UI needs course ids for the one-tap "Suggested: DDDM · BYOB" chips.

### D-010 · Dropping a card back on Needs Review
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Sticky: `classification='manual'`, `course_id=null`** | 5 | 5 | 5 | 4 |
| Reset to `unresolved`, so the next sync may re-file it | 3 | 5 | 3 | 2 |
| Ask the user each time | 4 | 2 | 3 | 2 |

This is a deliberate correction, and the rule is that manual wins. Undo still restores the previous state.

### D-011 · Informational notifications
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Every notification becomes a work item; `kind='info'` renders collapsed and muted, and is left out of the Agenda unless dated** | 5 | 5 | 4 | 4 |
| Drop info notifications | 2 | 5 | 4 | 2 |
| Keep them in a separate feed | 4 | 3 | 3 | 3 |

This matches §10 ("default: shown, collapsed"). Hide stays one click away. It also lets the classifier's guesses
on info items be corrected.

### D-012 · Contrast fixes (WCAG AA gate)
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Keep spec hues for UI (≥3:1). Add `*-text` variants for small text (≥4.5:1). Darken light `text-faint` (#9A948A→#6F6A60), dark `text-faint` (#6E6A62→#8C877D), light `accent` UI (#B08D57→#A0804B)** | 5 | 4 | 5 | 4 |
| Use spec values, ignore AA for meta text | 1 | 5 | 3 | 3 |
| Only ever use muted text | 4 | 5 | 3 | 2 |

The spec's own values fail AA as small text: light faint 2.5:1, brass accent 2.6:1, warning 3.1:1, dark faint 3.1:1.
`npm run check:contrast` checks 80 pairs across both themes and fails CI on any regression.

### D-013 · Offline demo backend
| Branch | C | S | M | D |
|---|---|---|---|---|
| **`Backend` interface with `SupabaseBackend` and `DemoBackend` (fixture data from the real Python pipeline, localStorage)** | 4 | 4 | 4 | 5 |
| MSW-mocked Supabase + API | 4 | 2 | 3 | 4 |
| Require a Supabase project for any UI work | 5 | 3 | 3 | 1 |

This drives the E2E suite and lets the owner try the app before any infrastructure exists. It also adds a
seam around data access. `demo-data.json` is produced by `python -m eztracker.devdata_export`, so demo
classifications are exactly what production does.

### D-014 · Undo
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Each user action's events share an `undo_token`; undo replays their `from_value`s (plus reverses learned aliases). Valid 30s, single use.** | 5 | 4 | 5 | 5 |
| Snapshot table of item rows | 4 | 3 | 3 | 4 |
| Client-side inverse mutation | 2 | 4 | 2 | 4 |

History and undo share one source of truth (`work_item_events`).

### D-015 · Keyboard drag and drop — **backtrack**
| Branch | C | S | M | D |
|---|---|---|---|---|
| ~~dnd-kit `KeyboardSensor` with a column-jumping coordinate getter~~ | 2 | 3 | 3 | 3 |
| **dnd-kit for pointer and touch; a small keyboard state machine: Space lifts, ←/→ picks a column, Space/Enter drops, Esc cancels, with `aria-live` announcements** | 5 | 4 | 4 | 4 |
| Keyboard users only get "Move to…" | 3 | 5 | 4 | 2 |

The first branch failed in the browser. dnd-kit's keyboard sensor scrolls a horizontally scrolling container
instead of moving across columns, so arrows did nothing on the Board. I backtracked to branch 2. The E2E test
"keyboard drag and drop" covers it. "Move to…" (press **M**) remains the alternative.

### D-016 · Due-date extraction policy
| Branch | C | S | M | D |
|---|---|---|---|---|
| **A date counts only after a deadline trigger (by, due, before, deadline, till…). A date without a time means 23:59 IST. Always flagged "parsed" for confirmation.** | 5 | 4 | 4 | 4 |
| Any date in the text | 2 | 5 | 3 | 2 |
| dateparser `search_dates` | 3 | 5 | 3 | 3 |

Month and weekday regexes use full or standard abbreviations only, so "Session 7 **Mar**keting" is not 7 March
and "this **mon**th" is not Monday. Covered by tests.

### D-017 · Adapter file layout
| Branch | C | S | M | D |
|---|---|---|---|---|
| **`adapters/{base,json_strategy,dom_strategy,surfaces}.py` — strategies hold per-surface classes; `surfaces.py` wires fallback** | 5 | 4 | 4 | 3 |
| Three files per §3 (`courses.py`, …), each with both strategies | 5 | 3 | 3 | 3 |
| One module | 4 | 4 | 2 | 3 |

Strategies share a lot of code within each strategy, and little across surfaces.

### D-018 · Phone navigation
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Bottom tab bar under 768px; the left rail from md up** | 5 | 4 | 4 | 5 |
| Hamburger drawer | 4 | 4 | 4 | 3 |
| Squeeze the 64px rail | 3 | 5 | 4 | 2 |

### D-019 · App sign-in
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Supabase magic link with `shouldCreateUser:false`; public sign-ups disabled after the owner registers** | 5 | 5 | 5 | 4 |
| Password auth | 4 | 4 | 4 | 3 |
| No app auth (single user) | 1 | 5 | 3 | 4 |

### D-020 · Seed data
| Branch | C | S | M | D |
|---|---|---|---|---|
| **`seed.sql` generated from the real pipeline (`scripts/gen_seed_sql.sh`); events inserted without ids; no calendar token in the seed. `make seed` produces relative dates** | 5 | 4 | 5 | 4 |
| Hand-written SQL | 3 | 3 | 2 | 3 |
| Python seeding only | 4 | 5 | 4 | 3 |

A static calendar token in a committed file would be a leak, and fixed event ids collide with real history.
Both problems were found by `db_test.sh --seed` and fixed.

### D-021 · Reading Nexus after discovery (supersedes the "unpinned" part of D-005)
Discovery (2026-09-27) found that Nexus is a Next.js RSC front end over a Bearer-token JSON API at
`api-students.mesaschool.co.in/api/v1`.

| Branch | C | S | M | D |
|---|---|---|---|---|
| **Keep capture: Playwright opens the Nexus pages, the SPA calls its own API with its own token, and we read the JSON. Pinned in `endpoints.json`. The token never enters EZTracker's code** | 5 | 4 | 5 | 4 |
| Extract the access token (`/api/auth/refresh`) and call the API with httpx | 5 | 4 | 3 | 4 |
| Parse the RSC payloads / DOM | 2 | 2 | 1 | 2 |

Branch 2 would be faster, but it means EZTracker handles a live Nexus session token. It also depends on an
undocumented auth route. Branch 1 costs a few extra page loads, well within the 5-minute budget.
`/assignments/my` already includes description, instructions and materials, so assignment detail pages are
no longer visited. Notifications carry exact `data.courseId` / `assignmentId`. The notification link is built
from them, so the existing +0.8 "known course/assignment id" signal from §7 applies and those items auto-file.

### D-022 · "Nothing missed": completeness sweep and coverage audit
| Branch | C | S | M | D |
|---|---|---|---|---|
| **After the three surfaces, visit every course page (full announcements, course-only assignments), My Work → Forms and the Calendar. Page notifications to `hasMore:false`. Audit every list-bearing API response and warn about any EZTracker doesn't read** | 5 | 3 | 5 | 5 |
| Only the three surfaces, incremental | 3 | 5 | 4 | 3 |
| Mirror every endpoint blindly | 3 | 2 | 2 | 2 |

Duplicates are prevented by the pipeline, which de-duplicates on the Nexus object id (`announcementId`,
`eventId`). Calendar events become items only when they look like work (exam, deadline, submission…), so
ordinary class sessions don't flood the Board. Cost is about 20 extra page loads per run, within the 5-minute
budget. Links: `safe_nexus_url` only emits verified Nexus routes with real UUIDs, and otherwise falls back to
the section's list page. This fixes the 404s from demo fixture ids.

### D-023 · Exact deep links, and lessons from the first real syncs
| Branch | C | S | M | D |
|---|---|---|---|---|
| **Mirror Nexus's own notification click handler (read from its bundle) for every link. Classify by `data.courseId` / `assignmentId` instead of by what's in the URL** | 5 | 4 | 5 | 5 |
| Link to the course or list page | 3 | 5 | 4 | 2 |
| Guess routes | 1 | 5 | 1 | 2 |

The first real syncs found three silent misses. Each is fixed and has a regression test:
1. **Pre-Term course dropped.** `best_list` pooled all responses and pruned the lower-scoring one. The Pre-Term
   course has no instructor, so its list was discarded. `lists_per_body` now judges each response on its own.
2. **MRS assessments and term names unread.** Found by the coverage audit, which now records key names and
   types of any unread list (never values), so it can be mapped without seeing data.
3. **Needs Review never re-checked.** `reclassify_unresolved` runs every sync. It only touches `unresolved`
   items, never manual ones.
