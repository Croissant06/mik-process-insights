# Independent Technical Audit — MIK Process Insights

| | |
|---|---|
| Repository | `Croissant06/mik-process-insights` (private) |
| Branch / commit audited | `development` @ `e84b28bf1193a59db722ffcf9e86a434c2388710` ("Allow all past dates in calendar…"), 17 Nov 2026 |
| Auditor | Claude, independent review thread (did not build the app) |
| Date | 17 Nov 2026, ~23:10 Sofia time |
| Mode | Read-only. No commits, branches, pushes, PR comments or deployments. All test data synthetic and in a throwaway local database. |

Note: another thread was adding `docs/business/` and preparing a `development → main` PR at the same time. At audit time those were not on `origin/development`, so they are not covered here.

---

## 1. Executive summary

The application is a **small, well-structured first version**: one FastAPI app, one form, two tables, a versioned YAML questionnaire and a well-built Bulgarian UI. The code is short, easy to read and mostly follows the decisions in `docs/DECISIONS.md`. I found **no SQL injection or XSS**, the migration **works on real PostgreSQL 16** and matches the models, and the 19 existing tests pass.

It is **ready to merge to `main` as a development baseline**. It is **not ready to collect real employee data**, as expected at this stage. The real-data blockers are mostly not code. They are a privacy notice and legal basis for employee data, a decision on hosting and network exposure, backups, and abuse protection on an endpoint that anyone on the network can call.

The most important code findings, all verified by running them:

1. **Only SQLite is tested, and two PostgreSQL-only crashes are hidden.** On Postgres, a questionnaire version with `department.required: false` or `name.max_length > 120` makes every matching submission fail with HTTP 500. Both pass on SQLite. Today's v1 does not trigger them, but both are documented as normal configuration changes.
2. **Cross-site and abusive submissions are accepted.** The API accepts JSON sent as `text/plain` from any origin (a classic CSRF path), has no request size limit (a 20 MB body was accepted), and has no rate limit. Anyone who can reach the server can submit reports under any employee's name.
3. **Malformed Unicode causes a 500 with a full stack trace in the log.** A lone surrogate (`\ud800`) in any text field crashes the insert.
4. **Unsafe default database.** If `DATABASE_URL` is missing, the app silently uses a SQLite file inside the container, and that data would be lost on rebuild.
5. **Dependencies are not pinned.** Versions are open ranges in both `pyproject.toml` and the `Dockerfile`. Tonight they resolved to Starlette 1.10, FastAPI 0.163 and SQLAlchemy 2.1, so Presiyan's Docker build can differ from what was tested.

None of these is hard to fix. The quick fixes add up to about **half a day**.

## 2. Overall assessment and scores

| Category | Score | One-line reason |
|---|---|---|
| 1. Architecture & code quality | **8/10** | Clean, small, right-sized. Weak spots: no logging or error handling layer, and sync DB calls inside an async route. |
| 2. Security & privacy | **5/10** | No injection or XSS. But no CSRF or content-type check, no size or rate limits, no security headers, and no privacy notice. Fine for local development, not for real data. |
| 3. Database & data integrity | **7/10** | Good versioning model and JSONB, and the migration is correct. Weak spots: YAML vs DB constraints are not cross-checked, there is no idempotency key, and backdating has no limit. |
| 4. Frontend & UX | **8/10** | Polished, responsive, Bulgarian, with keyboard support and correct states. Small accessibility gaps: success is not announced, and the department field is always marked required. |
| 5. Testing | **5/10** | Good unit coverage of validation and versioning, but SQLite only, no browser tests in the repo, and no abuse or edge-case tests. |
| 6. Production readiness | **3/10** | Expected for day 1: dev-only Compose, root container, no backups, no lock file, no hosting decision. |
| **Overall** | **6.5/10** | A solid prototype. Merge it, then finish a short hardening list before any real employee uses it. |

## 3. What was verified and what was not

**Verified by running it (evidence in this audit run):**
- `pytest`: **19 passed** on SQLite (Python 3.13, FastAPI 0.163.2, Starlette 1.10.0, SQLAlchemy 2.1.9, Alembic 1.20.1, psycopg 3.3.9).
- **PostgreSQL 16.x** (local server, not Docker): `alembic upgrade head` succeeds. `alembic check` reports "No new upgrade operations detected", so the models and migration match. Columns are `jsonb` and `timestamptz` as intended.
- App running on Postgres with HTTP probes: valid submission 201; `text/plain` body with a foreign `Origin` processed (201 or 422 by content); 20 MB body accepted; lone surrogate gives 500; `NUL` stripped; `"20261117"` and `"2026-W47-2"` accepted as dates; `questionnaire_version: true` treated as version 1; 120 emoji name stored correctly; `<script>` stored as text, and the page escapes it; `/openapi.json` served (200); no security headers on `/`.
- Postgres with a v2 YAML (`department.required: false`, `name.max_length: 200`): **both give 500** (NOT NULL violation and varchar(120) overflow).
- Playwright (Chromium, `bg-BG` locale, browser timezone America/Los_Angeles) at 375 light/dark and 1440 dark: no horizontal overflow; empty submit shows 5 inline errors and focuses the first; the calendar uses the server's Sofia date; the year/month jump to 15.03.2024 works; Escape returns focus; "Други" moves focus to its text box; double-click sends only **1** request; the network-failure banner keeps entered data; "Попълни нов отчет" resets the date to today. On success, focus falls to `<body>` and nothing is announced.
- Git history: no `.env`, database files, dumps or exports were ever committed. Only `egg-info` was committed once and later removed. `.gitignore` covers real data well.

**Not verified (assumptions):**
- `docker compose up` on Windows / Docker Desktop. There is no Docker daemon in this environment. The Dockerfile and Compose file were reviewed by reading only.
- Safari, Firefox and real phones. A screen-reader pass (NVDA/VoiceOver). Formal WCAG contrast measurement (tokens look AA-compliant by inspection).
- Behaviour with several uvicorn workers or replicas. Load. Real network or hosting conditions.
- Legal statements below are engineering flags, **not legal advice**. They need confirmation by MIK-BG's DPO or lawyer.

---

## 4. Findings

Classification:
- **[Before merge]**: cheap to fix and worth doing before `main` becomes the reference branch.
- **[Before production]**: must be fixed before any real employee data is collected.
- **[Future]**: next iterations, or when building the admin, auth and export features.

### 4.1 Critical

No critical code defects. The two critical items are **process and privacy blockers for real data**, not code bugs:

**C1. No privacy notice or legal basis for processing employee data** — [Before production]
- Evidence: `app/templates/base.html:37` (footer one-liner only); `form.html:13` shows only the chip "Не е оценка на представянето". The YAML `notice` text (`daily_report.v1.yaml:9-11`) is never rendered in full. `docs/PROJECT_STATUS.md` lists retention and "who may see identifiable data" as open.
- Risk: collecting named daily work logs from employees is personal-data processing at work. It likely needs a GDPR Art. 13 notice (controller, purpose, legal basis, retention, recipients, rights). It may need a DPIA, given systematic recording of work activity, and may need employees or their representatives informed under Bulgarian labour rules. **Confirm with the DPO or lawyer.**
- Fix: a short Bulgarian information notice linked from the form (a "Как се използват данните" section or a modal), and a written retention period. Effort: 2–4 h of drafting, plus legal review time. No code risk.

**C2. The submission endpoint is open to anyone who can reach the server, and identity is unverifiable** — [Before production]
- Evidence: `app/routes/api.py:22-51` has no auth, no rate limit and no size limit. `respondent_name` is free text (`models.py:47`).
- Risk: anyone on the network can file reports as any colleague, spam the table, or submit very large bodies. With named data, a forged entry about a colleague is a real HR or privacy problem.
- Fix: decide the hosting exposure first (internal network or VPN only; never public). Then add (a) a body size limit and rate limit (see H2), and (b) either employee authentication, or at minimum record that names are self-declared and make admin views say so. Effort: 2–4 h for limits; auth is part of the Wed/Thu work.

### 4.2 High

**H1. PostgreSQL-only 500 errors from YAML settings the docs describe as safe** — [Before merge]
- Evidence (verified on Postgres 16):
  - `validation.py:120-123` sets `dept = None` when the department is optional and empty, but `models.py:48` / `0001_initial.py:51` declare `department_code NOT NULL`. Result: IntegrityError, 500.
  - `validation.py:112` takes `max_length` from YAML (any value), but the column is `String(120)` (`models.py:47`). With `max_length: 200` and a 150-character name: StringDataRightTruncation, 500.
  - SQLite ignores both, so the test suite cannot see them (`tests/conftest.py:27`).
- Fix: in `questionnaire.check_definition` (`questionnaire.py:32-67`), reject `respondent.name.max_length > 120` and `respondent.department.required: false`, or make the column nullable in a new migration if optional departments are really wanted. Add a test that runs against Postgres (see T1). Effort: 30–60 min.

**H2. No CSRF or content-type check, no request size limit** — [Before production; becomes High-critical once cookie auth exists]
- Evidence: `api.py:26` uses `await request.json()`, which parses any body regardless of `Content-Type`. Verified: `Content-Type: text/plain` plus `Origin: http://evil.example` is processed. A `text/plain` cross-site form POST needs no CORS preflight, so any web page an employee visits could submit on their behalf. A 20 MB body was accepted and fully parsed in memory.
- Fix: reject requests whose `Content-Type` is not `application/json` (415). Reject a foreign `Origin` or `Sec-Fetch-Site: cross-site` (403). Cap the body (e.g. 64 KB) in the route or reverse proxy. Add a simple per-IP rate limit at the proxy. Effort: 1–2 h. **This matters more for the admin pages**: if they use session cookies, they need the same Origin check or CSRF tokens on every state-changing request.

**H3. Malformed Unicode crashes the request (500) and dumps a stack trace** — [Before merge]
- Evidence: `validation.py:44-49` strips control characters but not lone surrogates. A JSON `"\ud800"` reaches psycopg and raises UnicodeEncodeError (verified, full traceback in the uvicorn log). SQLite fails the same way.
- Fix: in `_clean_text`, reject strings that fail `value.encode("utf-8")` (return `bad_type`), and normalise to NFC while there. Effort: 15 min plus a test.

**H4. Silent SQLite fallback when `DATABASE_URL` is missing** — [Before production]
- Evidence: `config.py:30-32` defaults to `sqlite:///…/local-dev.db`. In a container that file lives in the image layer and is lost on rebuild, and the app would appear healthy (`/healthz` does not touch the DB: `main.py:44-46`).
- Fix: require `DATABASE_URL` unless an explicit `APP_ENV=dev` is set. Make `/healthz` run `SELECT 1`. Effort: 30 min.

**H5. Dependencies not pinned; two separate dependency lists** — [Before merge]
- Evidence: `pyproject.toml:6-15` and `Dockerfile:5-6` repeat the same open ranges (`fastapi>=0.115`, …). There is no lock file. Tonight they resolved to Starlette **1.x** and SQLAlchemy **2.1**, and the test client already warns about deprecation. Presiyan's Docker build next week may get different major versions than tonight's tests.
- Fix: generate a lock (`pip-compile` or `uv lock`) into `requirements.txt` with hashes. Have the Dockerfile install `-r requirements.txt` only. Effort: 30 min.

### 4.3 Medium

| # | Finding | Evidence | Fix | Effort | When |
|---|---|---|---|---|---|
| M1 | **Duplicate submissions possible on retry.** If the response is lost after commit (flaky Wi-Fi on the floor), the user retries and two rows are stored. There is no idempotency key. | `form.js:120-150`, `api.py:44-50` | Client generates a UUID per form fill and sends it as `id`; server uses it as the PK with `ON CONFLICT DO NOTHING`, returning 201 with the same id. | 1 h | Before production |
| M2 | **Unlimited backdating to 2020-01-01, combined with no per-day uniqueness.** One person can file hundreds of reports for past dates; analysis by work date becomes unreliable. The 2020 floor is arbitrary (the project started Nov 2026). | `validation.py:29-36`, `.env.example:9`, DECISIONS row "every past day" | Get a management decision. Practical default: `MAX_BACKDATE_DAYS=7` and floor = pilot start date. Show a soft warning for backdated reports. | 15 min config + decision | Before production |
| M3 | **No logging or error handling layer.** No app logger, no request id, no exception handler. Unhandled errors return plain-text 500, and stack traces go to stdout with whatever values triggered them. | `main.py` (none), `api.py` | Add a JSON-safe exception handler (log the error type and request id, never the payload) and basic `logging.basicConfig`. | 1 h | Before production |
| M4 | **Async route doing blocking DB I/O.** `create_submission` is `async def` but uses a sync Session, which blocks the event loop during the insert. Harmless at 50 users, but it is a pattern the admin pages should not copy. | `api.py:23-51` | Read the body in an async handler and run the DB part in `run_in_threadpool`, or make it `def` and use a Pydantic model. | 30 min | Future (before admin) |
| M5 | **Docker image runs as root; dev Compose is the only Compose.** Compose bind-mounts `./app` and `./questionnaire` over the image, so the running code is the working tree. There is no restart policy and no web healthcheck. | `Dockerfile` (no `USER`), `docker-compose.yml:24-27` | Add `USER app`. Split into `compose.yml` (no bind mounts, `restart: unless-stopped`, healthcheck) and `compose.override.yml` for dev. | 1 h | Before production |
| M6 | **Password trap in `.env`.** The password is written twice (`POSTGRES_PASSWORD` and inside `DATABASE_URL`). The README says "edit the password if you like", but editing one breaks login. Changing it after the first `up` does nothing, because Postgres only applies it when the volume is initialised. | `.env.example:3,5`, `README.md:9` | Build `DATABASE_URL` from parts in `config.py`, or document "change both, and only before the first run (or `down -v`)". | 20 min | Before merge (docs) |
| M7 | **App connects as the Postgres superuser.** `POSTGRES_USER` is the cluster superuser, so a compromised app could drop the database or read other DBs. | `docker-compose.yml:5-8`, `.env.example` | In production, create a separate `mik_app` role with DML only, and run migrations with the owner role. | 1 h | Before production |
| M8 | **No backup or restore story.** Data lives only in the named volume `pgdata`; `docker compose down -v` deletes it. Nothing documents `pg_dump`, schedule, off-host copy or restore test. | `docker-compose.yml:16,29-30`, README | Nightly `pg_dump -Fc` to a gitignored, off-host location with retention, plus one documented and **tested** restore. | 2–3 h | Before production |
| M9 | **No security headers.** No CSP, `X-Content-Type-Options`, `Referrer-Policy` or `frame-ancestors`. The inline theme script needs a CSP hash. `/openapi.json` is public. | `base.html:9-17`, `main.py:36` | Small middleware adding headers (CSP with `sha256-` for the inline script); `openapi_url=None`. | 45 min | Before production |
| M10 | **Accessibility gaps.** The success view gets no focus or announcement (verified: focus on `<body>`). Ten empty `role="alert"` regions all fire at once on validation. The department `<select>` always has `aria-required="true"`, even when optional. | `form.html:126-135`, `form.html:3`, `form.html:36` | Focus the success `<h2>` (`tabindex="-1"`). Use one summary live region plus `aria-invalid` and `aria-describedby` on fields. Make `aria-required` conditional. | 1 h | Before production |
| M11 | **Free-text name hurts the planned de-identified export.** "Иван Петров", "Иван" and "и. петров" become different pseudonyms, so per-person analysis and erasure requests ("delete my data") depend on fuzzy matching. | `models.py:47`, `docs/ADMIN_EXPORT_REQUIREMENTS.md` (salted hash of the name) | When management decides named vs anonymous, prefer an employee list or code (select, or login identity) in the next questionnaire version, plus a nullable `employee_id` column. Decide **before** real collection starts. | Decision + 2–4 h | Before production (decision) |
| M12 | **Questionnaire startup sync is not concurrency-safe.** Each process inserts missing versions at startup. Two workers or replicas starting together race on the primary key, and one fails to boot. | `questionnaire.py:89-101`, `main.py:30-32` | Run the sync as a step after `alembic upgrade` (once), or use `INSERT … ON CONFLICT DO NOTHING`. | 30 min | Before production if >1 worker |

### 4.4 Low / optional improvements

| # | Finding | Evidence | Suggestion | When |
|---|---|---|---|---|
| L1 | `date.fromisoformat` accepts `20261117` and `2026-W47-2` (verified). Harmless, but stricter than needed is better. | `validation.py:131` | Match `^\d{4}-\d{2}-\d{2}$` first. | Future |
| L2 | `questionnaire_version: true` is accepted as v1 (`bool` is an `int`). | `api.py:30-32` | `type(version) is int`. | Future |
| L3 | Answers that are only whitespace-like Unicode (zero-width space, RTL mark) pass "required". | `validation.py:8,49` | Strip `​-‏‪-‮﻿` too. | Future |
| L4 | Old questionnaire versions are accepted forever, so a stale tab can still post v1 months later. This was intentional, but there is no upper bound. | `api.py:32`, DECISIONS | Accept the active and the previous version only, or mark retired versions in YAML. | Future |
| L5 | A form left open overnight keeps yesterday's "today" (server date rendered once). The server still validates correctly. It may even be desirable for night shifts. | `pages.py:32`, `datepicker.js` init | On `visibilitychange`, if the page is more than 6 h old, reload the date window (or show a hint). | Future |
| L6 | The questionnaire `version` is global, not per `code`. A second questionnaire type would collide. | `models.py:28`, YAML `code` | Make the key `(code, version)` when a second form appears. | Future |
| L7 | No `server_default=now()` on timestamps. Rows inserted outside the ORM (imports, fixes) need explicit values. | `0001_initial.py:42,49` | Add in the next migration. | Future |
| L8 | The seed script uses `date.today()` (container local time, UTC), not the Sofia date. | `scripts/seed_synthetic.py:44` | Use `today_local`. | Future |
| L9 | Stored text is raw, which is correct, but the CSV export must neutralise `=`, `+`, `-` and `@` prefixes (verified: `=HYPERLINK(...)` stored as-is). | export (future) | Escape on CSV export only; keep raw in DB and JSON. | Export work |
| L10 | uvicorn access logs record client IP and path. This is not in the DB, but it is personal data in Docker logs, and DECISIONS says "No IP stored". | uvicorn default | Note it in the privacy notice or retention plan, or set `--no-access-log` behind a proxy that rotates logs. | Before production |

### 4.5 Things done well (keep them)

- **Versioning model**: immutable snapshot plus checksum refusal (`questionnaire.py:89-101`). Old answers stay interpretable, and the label is stored once per version, not per row. This is exactly what the export needs.
- **Real columns for filter keys** (`work_date`, `department_code`, `questionnaire_version`, all indexed) and JSONB for answers keyed by stable ids.
- **Server-authoritative Sofia date**, also used by the picker. UTC `timestamptz` for `submitted_at`.
- **Strict allow-list validation**: unknown answer keys and unselected "other" texts are dropped, unknown codes are rejected, and the exclusive "none" option is enforced on the server.
- **No SQL built from strings** anywhere (ORM only). Jinja autoescape is on, and `datepicker.js` `innerHTML` only interpolates numbers and constants.
- Docker exposes the web port only on `127.0.0.1` and does not expose Postgres. `.gitignore` is thorough, and git history is clean.
- The UI is careful: 48 px tap targets, `prefers-reduced-motion`, a no-flash theme, self-hosted fonts (no third-party requests), a keyboard-operable calendar, and a double-submit guard.

---

## 5. Testing review

**Existing suite (`tests/test_submissions.py`, 19 tests): good coverage of** required fields, unknown codes, exclusive and "other" text, length limits, the date window (including 0 and unlimited), Sofia vs UTC boundaries, optional name, version immutability, old-version interpretability and malformed bodies.

**Gaps, by priority:**
- **T1 [Before merge]** Run the suite on PostgreSQL as well (e.g. a `TEST_DATABASE_URL` env var, with CI using a `postgres:16` service). This would have caught H1. Run `alembic upgrade head` in the test setup instead of `create_all`, so the migration itself is tested.
- **T2 [Before merge]** Regression tests for H1, H3, and later H2 (415 / 403 / 413).
- **T3 [Before production]** Commit the Playwright checks the builder ran ad hoc (load, empty submit, calendar, success, reset, offline banner) as a small `tests/e2e` suite. Today they live only as screenshots.
- **T4 [Future]** Startup with an invalid YAML or a missing version (`ACTIVE_QUESTIONNAIRE_VERSION` points to nothing); `MAX_BACKDATE_DAYS=abc` (currently crashes on startup with a raw `ValueError`; that is acceptable, but the message is unclear); concurrent startups (M12).

## 6. Architectural readiness for Wednesday/Thursday (admin, auth, export)

| Planned feature | Ready? | What could get in the way |
|---|---|---|
| Admin list with filters (date, department, version) | **Yes** | Indexed real columns already exist. Make routes `def` (M4) and add a session dependency instead of `app.state.session_factory()` everywhere. |
| Authentication | **Partly** | The design needs a decision: admin-only auth, or employees too (C2, M11)? If session cookies are used, H2's Origin/CSRF protection becomes mandatory on all POSTs. Plan a `users` table in a new migration; nothing current blocks it. |
| JSON / JSONL / CSV export | **Yes** | The snapshot join gives labels per version. Watch for: CSV formula escaping (L9), the name-based pseudonym weakness (M11), and empty optional answers stored as `""` (decide `""` vs `null` in the export spec). Add the optional `description` field to questions in v2, as the export doc suggests. |
| De-identified export | **Partly** | Free text can identify people (already noted in the export doc). Deciding name vs employee code **before** real data arrives is much cheaper than fixing it afterwards. |

## 7. Production readiness checklist (before real employee data)

**Governance and privacy**
- [ ] Privacy notice in Bulgarian on the form; legal basis and DPIA decision confirmed with the DPO or lawyer (C1)
- [ ] Retention period set, plus a documented deletion procedure (including "delete my data")
- [ ] Named vs anonymous vs employee-code decision (M11); who may see identifiable data
- [ ] Management decision on the backdating window and floor date (M2)
- [ ] Department list finalised in a new YAML version (v1 placeholders must not be used for real data)

**Security**
- [ ] Hosting decided: internal network or VPN only, HTTPS via a reverse proxy, never public
- [ ] Content-Type, Origin, body size and rate limits (H2)
- [ ] Security headers and `openapi_url=None` (M9)
- [ ] Least-privilege DB role (M7); strong secrets outside git; `.env` never shared in chat
- [ ] Admin auth in place before any admin view goes live

**Reliability and data**
- [ ] H1, H3, H4 fixed with tests; suite runs on Postgres (T1)
- [ ] Pinned and locked dependencies (H5)
- [ ] Production Compose: non-root, no bind mounts, restart policy, DB-checking healthcheck (M5, H4)
- [ ] Idempotent submissions (M1)
- [ ] Nightly backup, off-host copy, **restore tested once** (M8)
- [ ] Logging with request ids and no payloads in logs (M3); log retention defined (L10)
- [ ] `docker compose up` verified on Presiyan's Windows machine with a fresh volume

**UX**
- [ ] Success announced and focused; error live region tidied (M10)
- [ ] Tested on the devices employees will actually use (shared floor PC? phones?) and on Safari or Firefox

## 8. Recommended fix plan and effort

| Batch | Items | Effort |
|---|---|---|
| A. Quick wins before merge | H1, H3, H5, M6 docs, T1/T2 | ~3–4 h |
| B. Hardening before pilot | H2, H4, M1, M3, M5, M7, M9, M10, M12 | ~1–1.5 days |
| C. Operations | M8 backup and restore, hosting and HTTPS | ~0.5–1 day (depends on hosting) |
| D. Decisions (non-code) | C1, C2, M2, M11, department list | Meetings with Martin and the DPO |

## 9. Final recommendation

**Merge `development` into `main` as a baseline: yes.** Ideally do batch A first (half a day). If time is tight, merge now and log batch A as the first follow-up; nothing in it gets worse with time.

**Collect real employee data: not yet.** The code is a good foundation, and none of the issues needs a redesign. But real data should wait until batches B–D are done, above all the privacy notice and legal basis, the hosting and exposure decision, abuse limits, and a tested backup. The Wednesday/Thursday admin, auth and export work can go ahead on the current architecture. Settle the named-vs-employee-code question and add CSRF/Origin protection before or alongside it, not after.
