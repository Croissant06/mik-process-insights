# Decision log — MIK | Process Insights

| Date | Decision | Status | Why / notes |
|---|---|---|---|
| 2026-11-17 | Stack: FastAPI + Jinja2 (server-rendered) + plain CSS/JS, SQLAlchemy 2, Alembic, PostgreSQL, Docker Compose | Approved by Presiyan | One form + later one admin table; React would add a second app, build step and CORS for no user benefit. Can add HTMX later. |
| 2026-11-17 | Questionnaire defined in versioned YAML, snapshotted immutably into `questionnaire_versions` | Approved | Questionnaire not yet approved by management; changes must not need code/DB changes and must not break old data. |
| 2026-11-17 | Answers stored as JSON(B) next to `questionnaire_version`; core fields (name, department, work date, timestamp) are real columns | Implemented | Filtering by date/department stays cheap; question changes need no migration. |
| 2026-11-17 | All validation on the backend (`app/validation.py`); JS only renders returned errors | Implemented | Requirement from Presiyan. |
| 2026-11-17 | Work date = Europe/Sofia calendar day; timestamps UTC | Implemented | Requirement. Employee may pick today or yesterday (`MAX_BACKDATE_DAYS=1`) — assumption, adjust if not wanted. |
| 2026-11-17 | Name required/optional via `respondent.name.required` in YAML | Implemented | Named vs anonymous still open with management. |
| 2026-11-17 | Obstacles are checkboxes (screenshot showed radios), with exclusive "no obstacles" option and a text field for "Други" | Implemented | Multiple obstacles per day are likely. |
| 2026-11-17 | Submissions are accepted against any known questionnaire version, not only the active one | Implemented | A form opened before a change should not lose the employee's work. |
| 2026-11-17 | No IP/user-agent/device data stored; no duplicate-per-day restriction | Implemented | Data minimisation; revisit after talking to Martin. |
| 2026-11-17 | Departments are placeholders ("Отдел 1 (примерен)") | Open | Real list to be confirmed with Martin on 18 Nov. |
| — | Hosting, authentication, admin access, retention, who sees named data | Open | Not decided; no public deployment. |
| 2026-11-17 | Design system: tokens in `app/static/css/tokens.css`, reusable components in `components.css`; Inter (Cyrillic + Latin, self-hosted, OFL) and Lucide icons as an inline sprite; palette navy #14253D / accent #2563EB / bg #F5F7FA / success #16A34A | Implemented | Presiyan's UI direction. Admin pages should reuse these files. No CDN or external requests at runtime. |
| 2026-11-17 | Theme: follows system by default, toggle persists in localStorage, applied before first paint | Implemented | Per UI direction. |
| 2026-11-17 | Questionnaire questions may carry an optional `section` heading; the form groups them into numbered steps | Implemented | Helps low-literacy users see the form is short and structured. v1 was edited for this and for one help text before any shared deployment; from now on published versions are immutable. |
| 2026-11-17 | Motion kept minimal: press feedback, checkbox/tick transitions, one short staggered page entrance, drawn success check; all disabled under `prefers-reduced-motion` | Implemented | Form is used once a day, so brief delight is fine; nothing blocks interaction. |
