# Project status — MIK | Process Insights (code repository)

Companion to the planning notes kept in the project knowledge base. Last updated: 17 Nov 2026, evening.

## Verified tonight
- Employee form (Bulgarian, responsive, light/dark) renders from the YAML questionnaire; checked in a headless browser at desktop and 390px mobile widths, including inline errors and the success state.
- Backend validation, versioning, Sofia/UTC handling and persistence covered by the pytest suite (SQLite).
- Alembic migration applied on SQLite; the app ran end to end with synthetic submissions.

## Not verified
- **PostgreSQL / Docker Compose were not run** (no Docker daemon in the build environment). The Postgres migration and `docker compose up` still need a first run on Presiyan's machine.
- Tested only with synthetic data, no real users, no accessibility audit beyond basic keyboard/focus/contrast choices.

## Not built yet (planned Wed/Thu)
Admin view (date/department filter, search), authentication, CSV/Excel export, basic aggregate insights, department configuration screen.

## Open questions (with Martin, 18 Nov)
Real departments · participant list · employee device access (sewing floor?) · hosting · named vs anonymous submissions · retention · who may see identifiable data · MES/AI scope.

## Next
1. Run `docker compose up` locally and confirm the Postgres path.
2. Management feedback → `daily_report.v2.yaml`.
3. Admin dashboard + auth design once hosting is known.
