# AI handoff — shared channel between Claude and ChatGPT

**Source of truth: this GitHub repository. Final decisions: Presiyan.**

## Roles and rules
- **Claude**: development and implementation (code, tests, docs, PRs on `development`).
- **ChatGPT**: independent technical review, business analysis, strategic planning.
- **Presiyan** decides. Neither assistant merges PR #1 or changes scope without his explicit go-ahead.
- **Read this file at the start of every session. Update it after every significant change** (merged/pushed work, test results, decisions, new issues, review answers). Keep it short and factual.
- Separate **confirmed facts** from **assumptions**; mark assumptions as such. Never invent company data.
- **Never put in this file or the repo:** real employee data, submissions, database dumps, exports, credentials, or `.env` contents. Synthetic data only. No public deployment.
- Talk to Presiyan in English; employee-facing UI and company documents in Bulgarian.
- Detail lives elsewhere; link, don't copy: `docs/PROJECT_STATUS.md`, `docs/DECISIONS.md`, `docs/REMEDIATION_CHECKLIST.md`, `docs/audit/`, `docs/ADMIN_EXPORT_REQUIREMENTS.md`, `README.md`.

## 1. Current project status (last updated 2026-11-17, late evening)
- **Product:** MIK | Process Insights, an internal Bulgarian web form where employees spend ~5 min/day describing tasks, repeated work and obstacles for MIK-BG (clothing manufacturer, Ruse). A discovery tool, not employee evaluation.
- **Deadlines:** platform ready Thu 19 Nov; preliminary results to management Wed 25 Nov.
- **State:** employee form is built and approved by Presiyan (design and behaviour). PR #1 (`development` → `main`) is open, **not merged**. Admin dashboard, authentication and export are **not built** (planned Wed/Thu).
- **Verdict of the independent audit (17 Nov):** fine as a baseline; **not ready for real employee data**.
- **Hosting:** provisional only (see section 4).

## 2. Completed
- Stack scaffold, versioned YAML questionnaire with immutable DB snapshots, backend validation, Sofia/UTC dates, JSONB answers.
- Responsive Bulgarian form, design system (tokens/components, Inter, Lucide, light/dark), Bulgarian calendar picker (unlimited past dates by default, no future).
- Five Bulgarian business drafts in `docs/business/`; future export requirements recorded.
- Audit batch A: H1, H3, H4, H5, M6, T1/T2 (see `docs/REMEDIATION_CHECKLIST.md`).
- `main` created as an empty root commit so PR #1 can show the whole project.

## 3. Latest commits and test results
| Commit | What |
|---|---|
| cea114c | Test stage of the Dockerfile copies `Dockerfile` and `.env.example` (fixes 2 Docker-only test failures) |
| acb43fd | Audit fixes H1, H3, H4, H5, M6 + PostgreSQL tests, docs, remediation checklist |
| 752d83c | Merge of empty `main` root into `development` |
| 3081394 | Bulgarian business documents + questionnaire document generator |

Test results (confirmed):
- Cloud environment, PostgreSQL 16 via real Alembic migration: **45 passed**. SQLite: 41 passed, 4 Postgres-only skipped.
- Presiyan's Docker run before cea114c: 43 passed, 2 failed (files missing in the test image). Fixed in cea114c; verified here by simulating the image layout (45 passed). **Presiyan's re-run in Docker is still to be confirmed.**
- Presiyan ran the app in Docker and confirmed submissions and JSONB answers are stored in PostgreSQL.
- **Not verified:** the multi-stage Docker build and Compose healthcheck end to end, real phones, Safari/Firefox, formal accessibility audit.

## 4. Architectural decisions (full list: `docs/DECISIONS.md`)
- FastAPI + Jinja2 (server-rendered), plain CSS/JS, SQLAlchemy 2, Alembic, PostgreSQL 16, Docker Compose.
- Questionnaire in versioned YAML; published versions are immutable (checksum guard at startup); old versions stay valid.
- All validation on the backend. Work date = Europe/Sofia calendar day; timestamps UTC.
- Database from `DATABASE_URL` or `POSTGRES_*`; SQLite only with `APP_ENV=dev`; `/healthz` checks the DB.
- Dependencies hash-locked (`requirements*.txt`); same tests run on SQLite and PostgreSQL.
- PostgreSQL is the single source of truth; persistent volumes; never `docker compose down -v` on real data.
- **Provisional hosting (to discuss with Martin):** existing company computer or Linux server, Docker Compose, persistent PostgreSQL, internal network only, approved VPN for remote admin.
- Future export: JSON/JSONL/CSV, filters, de-identified option, no external AI APIs yet (`docs/ADMIN_EXPORT_REQUIREMENTS.md`).

## 5. Outstanding technical issues (priority order; details in `docs/REMEDIATION_CHECKLIST.md`)
1. **H2** no Content-Type/Origin check, no body-size or rate limit.
2. **M1** duplicate submissions on retry (no idempotency key).
3. **M3** logging/exception handler; **M5** non-root container and production Compose; **M7** least-privilege DB role; **M9** security headers; **M10** accessibility; **M12** startup sync race with more than one worker.
4. **M8** backups and a tested restore.
5. Low items L1–L10, tests T3/T4.

## 6. Pending management decisions (with Martin, 18 Nov; **assumptions until answered**)
- Real department list, participants, employee device access (sewing floor?).
- Hosting and exposure (confirm the provisional plan).
- Named vs anonymous vs employee code (affects the de-identified export and erasure requests).
- Backdating limit and floor date; retention period; who may see identifiable data.
- Privacy notice and legal basis (DPO/lawyer); MES/AI scope.

## 7. Upcoming tasks and priorities
1. Presiyan: re-run the Docker test command and confirm 45 passed; confirm calendar shows all past days after removing `MAX_BACKDATE_DAYS=1` from his local `.env`.
2. Collect Martin's answers (18 Nov); turn management feedback into `daily_report.v2.yaml`.
3. Wed/Thu: admin dashboard + authentication + export, with Origin/CSRF protection from the start (H2).
4. Remediation batches B–D before any real employee data.
5. Bulgarian business documents need native-speaker and legal review.

## 8. Review requests
| # | To | Request | Status |
|---|---|---|---|
| 1 | ChatGPT | Independent review of PR #1 (code, security, privacy approach); compare against `docs/audit/TECHNICAL_AUDIT_2026-11-17.md` | Open |
| 2 | ChatGPT | Review `docs/business/*_BG.md` for business sense and wording; flag anything stated as fact that is only an assumption | Open |
| 3 | ChatGPT | Review `docs/REMEDIATION_CHECKLIST.md` priorities and the provisional hosting approach | Open |

## 9. Communication log
Newest entry at the top. Format: `date · from → to · message`. Keep entries short; link commits or files.

- 2026-11-17 · Claude → ChatGPT · Created this file. PR #1 is open and unmerged; audit batch A is done (commits acb43fd, cea114c). Please start with review requests 1–3 above and answer in this log or as PR comments. Presiyan has final say.
