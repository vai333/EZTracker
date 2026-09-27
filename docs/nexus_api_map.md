# Nexus API map

_Recorded on 2026-09-27 from the owner's logged-in session in the Claude desktop browser pane. This file has
**shapes only**: key names and types, never values. IDs appear as `{uuid}`. Tokens, names, emails and phone
numbers are not recorded._

## Topology

| Host | What |
|---|---|
| `students.mesaschool.co.in` | Next.js App Router front end. Pages load as React Server Component payloads (`?_rsc=`), with no page JSON. |
| `students.mesaschool.co.in/api/auth/*` | Next.js auth routes: `POST login` (form login) and `POST refresh` (JSON body → `{data:{accessToken, user}}`; the refresh token lives in an httpOnly cookie). |
| `api-students.mesaschool.co.in/api/v1/*` | **JSON REST API** called from the browser with `Authorization: Bearer <accessToken>`, `credentials: include`. |

Login is a plain **email/student-ID + password** form at `/login`, with no SSO or CAPTCHA seen, so automated login
(§5) works. The scraper **never handles the access token**. It logs in with Playwright, lets the Nexus pages make
their own calls, and reads the JSON responses (see `scraper/endpoints.json`).

## Endpoints used by EZTracker

### Courses: `GET /api/v1/curriculum/courses?termId={uuid}`
Called once per term tab on `/student/lms/courses` (the tabs are Pre-Term and Term 1, and the term list is
server-rendered).
```json
{ "data": { "courses": [ {
  "id": "uuid", "title": "string", "shortName": "string", "instructorName": "string|null",
  "courseType": "string", "classType": "string", "termId": "uuid", "coverImageUrl": "string",
  "description": "string|null", "code": "null", "sequence": "null", "startDate": "null", "endDate": "null",
  "visible": "boolean", "createdAt": "iso", "updatedAt": "iso" } ] } }
```
`courseType` is the "Core" / "Soft Skills" badge and `classType` is "In Class" / "Hybrid". `shortName` is
Nexus's own short name, and EZTracker uses it.

### My Work: `GET /api/v1/assignments/my`
Called on `/student/lms/assignments`. One call returns **everything**, including description and instructions,
so no detail pages are needed. 36 items at the time of recording.
```json
{ "data": { "assignments": [ {
  "id": "uuid", "title": "string", "courseId": "uuid|null", "courseTitle": "string|null",
  "dueAt": "iso|null", "cutoffDate": "iso|null", "allowLate": "boolean", "allowSubmissionsFrom": "iso",
  "description": "html|null", "instructions": "html|null",
  "materials": [ { "id": "uuid", "title": "string", "kind": "string", "url": "string", "fileName": "string",
                   "fileType": "string", "fileSizeBytes": "number", "position": "number" } ],
  "isGroup": "boolean", "groupSize": "null", "groupingId": "null", "leaderId": "uuid|null",
  "mySubmissionStatus": "\"submitted\"|null", "status": "\"published\"",
  "submissionType": "\"any\"|\"link\"|\"file\"|\"text\"", "maxAttempts": "number|null",
  "maxMarks": "string|null", "topicId": "uuid|null", "restrictions": [], "selectedGroupIds": [],
  "createdAt": "iso", "publishedAt": "null" } ] } }
```
Forms: `GET /api/v1/forms/mine` → `{data:{forms:[]}}`. It was empty when recorded, so its shape is not yet known.

### Notifications: `GET /api/v1/notifications?limit=20[&before={createdAt iso}]`
Cursor pagination: each "load more" passes `before=` set to the oldest `createdAt`.
```json
{ "data": { "hasMore": "boolean", "unread": "number", "items": [ {
  "id": "uuid", "type": "string", "title": "string", "body": "html (short, ≤ ~120 chars)",
  "createdAt": "iso", "isRead": "boolean", "data": { "…": "depends on type" } } ] } }
```
| `type` | `data` keys | Nexus tab |
|---|---|---|
| `announcement` | `courseId`, `announcementId` | Announcement |
| `assignment_new` | `courseId`, `assignmentId` | Assignment |
| `system` | `url`, `source` | General (e.g. "Your BYOB leaderboard has been updated") |
| `ticket_update` | `ticketId`, `status` | General (support tickets) |
| event (title "Event updated") | `eventId`, `action`, `subtype` | Course Calendar |

**Classification consequence:** announcements and new-assignment notifications name their course **exactly**,
through `data.courseId`. The classifier treats that as the §7 "known course id" signal (+0.8), so they file
automatically. The fuzzy text signals still decide `system` notifications and anything without a course id.

### Announcements (full text): `GET /api/v1/announcements?courseId={uuid}`
Called when a course page loads (`/student/lms/courses/{uuid}`). The response shape was **not recorded**, because
the app served it from cache during recording. The mapper uses tolerant keys (`id`, `title`, `body`/`content`,
`createdAt`) and matches by `data.announcementId`. The first real sync logs a warning if it can't find them.

### Deep links: where "Open in Nexus" goes
These mirror Nexus's own notification click handler, recorded from its front-end code:

| Nexus object | Route |
|---|---|
| announcement / reply | `/student/community/{announcementId}?src=notification` (opens that exact post) |
| assignment (new, due, graded) | `/student/lms/assignments/{assignmentId}` |
| calendar event (`system` + `subtype: calendar_event`) | `/student/lms/calendar` |
| Mesa Readiness Score assessment | `/student/lms/mesa-readiness-score/{slug}` |
| other `system` notifications | the notification's own `data.url` if it's a known route, else `/student/lms/notifications` |

### Terms: `GET /api/v1/curriculum/terms`
`{data:{terms:[{id, programId, name, sequence, minElectives, createdAt, updatedAt}]}}` supplies the term label for
each course's `termId`. Both terms' course lists load on the first Courses page view.

### Mesa Readiness Score: `GET /api/v1/mrs/assessments`
`{data:{visible, maxMarks, assessments:[{slug, title, blurb, status, tint, mrsScore, totalMarks, partsSubmitted}]}}`
Each assessment becomes an item under a synthetic "Mesa Readiness Score" course. It counts as submitted when all
3 parts are in or a score exists.

### Course visibility
`curriculum/courses` also returns courses with `visible: false`, which Nexus hides. EZTracker creates those
archived.

### Seen but unused
`GET /api/v1/student/me`, `/curriculum/courses/{uuid}`, `/curriculum/topics?courseId=`,
`/assignments?courseId={uuid}&status=published`, `/content/topics/{uuid}/materials`, `…/recordings`,
`/coach/scenarios`.

## Page routes
`/login` · `/student/lms/courses?term={uuid}` · `/student/lms/courses/{uuid}` · `/student/lms/assignments` ·
`/student/lms/assignments/{uuid}` · `/student/lms/notifications` · `/student/lms/calendar` ·
`/student/lms/attendance`
