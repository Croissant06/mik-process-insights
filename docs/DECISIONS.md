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
