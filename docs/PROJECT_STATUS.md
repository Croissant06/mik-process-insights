# Project status — MIK | Process Insights (code repository)

Companion to the planning notes kept in the project knowledge base. Last updated: 17 Nov 2026, evening.

## Verified tonight
- Employee form (Bulgarian, responsive, light/dark) renders from the YAML questionnaire; checked in a headless browser at desktop and 390px mobile widths, including inline errors and the success state.
- Backend validation, versioning, Sofia/UTC handling and persistence covered by the pytest suite (SQLite).
- Alembic migration applied on SQLite; the app ran end to end with synthetic submissions.

- UI design pass (tokens, components, Inter, Lucide, persistent light/dark theme) checked with Playwright at 375, 768 and 1440 px in light and dark: no horizontal overflow, no unexpected console errors, theme persists after reload, Inter loads. Screenshots: `ui-review/` in the project files.
- Calendar date picker checked with Playwright (browser clock set to a non-Sofia timezone): default = server Sofia date, future and out-of-window days disabled, keyboard navigation, Enter/Escape/«Днес», reset after submit, tampered future date rejected with 422. Screenshots in `ui-review/calendar/`.
- Calendar now allows every past day by default (month/year selects); checked in Playwright incl. picking 15.03.2024 end to end. Screenshots in `ui-review/calendar/`.

## Not verified
- **PostgreSQL / Docker Compose were not run** (no Docker daemon in the build environment). The Postgres migration and `docker compose up` still need a first run on Presiyan's machine.
- Tested only with synthetic data, no real users. No formal accessibility audit (WCAG) and no test on real phones or Safari/Firefox; only Chromium was used. Context7 was not available, so no library docs were consulted.

## Business documents prepared (Bulgarian, `docs/business/`) — all drafts
- `QUESTIONNAIRE_BG.md` — generated from the questionnaire YAML (`python scripts/generate_questionnaire_doc.py`; a test fails if it is out of date), initiative summary and an empty participant-list template.
- `ORDER_TRACKING_BG.md` — template for tracking a real order (activities, roles, software, information flow, work vs waiting time, duplicated information, approvals, obstacles). Stages are examples only, not verified.
- `EMPLOYEE_INTERVIEWS_BG.md` — short interview guide and note template.
- `MANAGEMENT_QUESTIONS_BG.md` — checklist for Martin and Miglena (MES/AI, departments, participants, devices, hosting, privacy, retention, 25 Nov meeting).
- `EMPLOYEE_NOTICE_BG.md` — proposed employee notice, **pending management approval**; contains placeholders, no legal claims.
None contains invented company or employee data. Wording was not reviewed by a native-speaker editor or a lawyer.

## Not built yet (planned Wed/Thu)
Admin view (date/department filter, search), authentication, CSV/Excel export, basic aggregate insights, department configuration screen.

## Open questions (with Martin, 18 Nov)
Real departments · participant list · employee device access (sewing floor?) · hosting · named vs anonymous submissions · retention · who may see identifiable data · MES/AI scope.

## Next
1. Run `docker compose up` locally and confirm the Postgres path.
2. Management feedback → `daily_report.v2.yaml`.
3. Admin dashboard + auth design once hosting is known.
