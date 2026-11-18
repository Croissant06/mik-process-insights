# Project status — MIK | Process Insights (code repository)

Companion to the planning notes kept in the project knowledge base. Last updated: 17 Nov 2026, late evening (after the independent technical audit).

## Verified tonight
- Employee form (Bulgarian, responsive, light/dark) renders from the YAML questionnaire; checked in a headless browser at desktop and 390px mobile widths, including inline errors and the success state.
- Backend validation, versioning, Sofia/UTC handling and persistence covered by the pytest suite (SQLite).
- Alembic migration applied on SQLite; the app ran end to end with synthetic submissions.

- UI design pass (tokens, components, Inter, Lucide, persistent light/dark theme) checked with Playwright at 375, 768 and 1440 px in light and dark: no horizontal overflow, no unexpected console errors, theme persists after reload, Inter loads. Screenshots: `ui-review/` in the project files.
- Calendar date picker checked with Playwright (browser clock set to a non-Sofia timezone): default = server Sofia date, future and out-of-window days disabled, keyboard navigation, Enter/Escape/«Днес», reset after submit, tampered future date rejected with 422. Screenshots in `ui-review/calendar/`.
- Calendar now allows every past day by default (month/year selects); checked in Playwright incl. picking 15.03.2024 end to end. Screenshots in `ui-review/calendar/`.

## Audit follow-up (17 Nov) — see `docs/REMEDIATION_CHECKLIST.md`
- Independent audit saved in `docs/audit/`. Verdict: fine as a baseline on `main`, **not ready for real employee data**.
- Done: H1 (config vs DB limits), H3 (malformed Unicode), H4 (no silent SQLite, DB-aware health check), H5 (hash-locked dependencies), M6 (credentials), T1/T2 (PostgreSQL tests + regression tests).
- Verified: full suite on PostgreSQL 16 through the real migration (45 passed) and on SQLite (41 passed, 4 Postgres-only skipped). Presiyan also ran the app in Docker and confirmed submissions and JSONB answers are stored in PostgreSQL.
- Provisional hosting: company computer or Linux server + Docker Compose + persistent PostgreSQL + internal network + approved VPN for remote admin (to discuss with Martin). Nothing deployed.

> PR #1 (`development` → `main`) was merged on 17 Nov 2026 as a baseline. Still no real data and no deployment.

## Pre-merge safeguards (ChatGPT review, 17 Nov late evening)
- **Local Docker verification (Presiyan):** `docker-compose.test.yml` run → 43 passed / 2 failed (files missing in the test image), fixed in cea114c; the re-run gave **45 passed, exit 0**. The app also ran in Docker with submissions and JSONB answers stored in PostgreSQL.
- **Form fails closed without JavaScript:** the form now has `method="post"` to `/js-required` (stores nothing, does not read the body, answers 400 in Bulgarian) and a `<noscript>` notice that hides the form; names and answers can never end up in a URL. The only submission path is still `POST /api/submissions` from `form.js`.
- **Destructive-test guard:** PostgreSQL tests wipe the schema, so they now require db name exactly `mik_test`, an approved local/throw-away host, and `ALLOW_DESTRUCTIVE_TESTS=1` (`tests/safety.py`, unit-tested).
- Business drafts improved without management decisions (core interview questions, order-tracking format advice, notice do-not-enter list, management-meeting priorities, `docs/business/README.md`); no questionnaire change (v1 is immutable; wording suggestions wait for a v2 agreed with management).
- Tests after these changes: PostgreSQL 16 **65 passed**; SQLite 61 passed, 4 skipped. Runtime check on PostgreSQL: `/healthz` 200, calendar floor 2020-01-01, form visible with JS and hidden with notice without JS.

## Admin panel (18 Nov)
- Built: personal admin accounts (max 4, created with `scripts/admin_users.py`), login/logout, filtered report list (department, dates, version), report detail, audit log, hardened session cookie, login throttle. Read-only; **no export yet**, no attachments yet. Migration `0002` is additive (existing data untouched).
- Also done: request protection H2 (JSON-only API, cross-site refused, 256 KB cap).
- Tests: PostgreSQL 16 119 passed; SQLite 115 passed, 4 skipped. Browser check (Playwright, PostgreSQL, synthetic data) at 375 and 1440 px in light and dark: login, bad password, list, detail, logout; no overflow, no console errors on the normal flow. The browser test found a real bug (admin `Referrer-Policy: no-referrer` made form posts carry `Origin: null` and get refused); fixed and covered by tests.
- Still needed: the four real accounts (with Presiyan), hosting + HTTPS, export, attachments (needs questionnaire v2 + privacy decision).

## Not verified
- **Docker was not run in the cloud build environment** (no daemon): the new multi-stage Dockerfile, the Compose web healthcheck and `docker-compose.test.yml` still need a run on Presiyan's machine (`docker compose up --build`, then the test command in the README). PostgreSQL itself was tested directly (see above).
- Tested only with synthetic data, no real users. No formal accessibility audit (WCAG) and no test on real phones or Safari/Firefox; only Chromium was used. Context7 was not available, so no library docs were consulted.

## Business documents prepared (Bulgarian, `docs/business/`) — all drafts
- `QUESTIONNAIRE_BG.md` — generated from the questionnaire YAML (`python scripts/generate_questionnaire_doc.py`; a test fails if it is out of date), initiative summary and an empty participant-list template.
- `ORDER_TRACKING_BG.md` — template for tracking a real order (activities, roles, software, information flow, work vs waiting time, duplicated information, approvals, obstacles). Stages are examples only, not verified.
- `EMPLOYEE_INTERVIEWS_BG.md` — short interview guide and note template.
- `MANAGEMENT_QUESTIONS_BG.md` — checklist for Martin and Miglena (MES/AI, departments, participants, devices, hosting, privacy, retention, 25 Nov meeting).
- `EMPLOYEE_NOTICE_BG.md` — proposed employee notice, **pending management approval**; contains placeholders, no legal claims.
None contains invented company or employee data. Wording was not reviewed by a native-speaker editor or a lawyer.

## Not built yet
CSV/JSON/JSONL export, file/photo attachments, basic aggregate insights, department configuration screen (waiting for Martin's department names).

## Open questions (with Martin, 18 Nov)
Real departments · participant list · employee device access (sewing floor?) · hosting · named vs anonymous submissions · retention · who may see identifiable data · MES/AI scope.

## Next
1. Run `docker compose up --build` and the Compose test command locally to confirm the new Docker setup.
2. Management feedback → `daily_report.v2.yaml`.
3. Admin dashboard + auth design once hosting is known (include Origin/CSRF protection from the start).
4. Work through `docs/REMEDIATION_CHECKLIST.md` batches B–D before any real employee data.
