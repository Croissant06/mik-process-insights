# Admin dashboard — AI-ready data export (requirement, NOT built yet)

Recorded 17 Nov 2026 at Presiyan's request. Planned for the admin phase (Wed/Thu or later). **No export code and no external AI API integration exists or is planned for tonight.**

## Requirements
- PostgreSQL stays the single source of truth; persistent Docker volume (`pgdata` in `docker-compose.yml` survives `docker compose down`; only `down -v` deletes it); existing JSONB submission design is kept.
- Export formats: **JSON, JSONL, CSV**; UTF-8 (CSV with BOM option for Excel).
- Filters: department, date range (work date), questionnaire version.
- **Anonymized / de-identified option** for AI-assisted analysis.
- Stable question identifiers **and** human-readable question descriptions.
- Original Bulgarian responses preserved verbatim.
- Export metadata + questionnaire version information included.
- Structured for LLMs, Python scripts and classic tools (pandas, Excel).
- Never commit real submissions, dumps, production exports or credentials. Only synthetic datasets in the repo (`datasets/synthetic/`).

## How the current design already supports this
- Question ids (`tasks`, `obstacles`, …) and option codes (`waiting`, …) are stable; labels, help text and department labels live in the immutable `questionnaire_versions` snapshot, so every record can be joined to its exact wording.
- Answers are JSONB keyed by question id; core fields are real columns, so filtering is cheap.

## Proposed export shape (to confirm when building)
```
{ "export": {"generated_at_utc", "format_version", "filters", "anonymized": true|false, "record_count"},
  "questionnaires": { "1": { full definition incl. labels/descriptions } },
  "records": [ {"id", "questionnaire_version", "work_date", "submitted_at_utc", "department_code",
                "respondent": "<omitted | pseudonym>", "answers": {...}} ] }
```
- JSONL: one record per line, preceded by a metadata line (or sidecar `*.meta.json`). CSV: one row per submission, columns named by question id, multi-choice as `;`-joined codes, plus a sidecar data dictionary (id → Bulgarian label, description, type).
- Suggested small change when building: add an optional `description` (what the question is for, in plain language) to question definitions in the next questionnaire version, for LLM context.

## De-identification — caveats to agree with management
- Default anonymized export: drop `respondent_name`, replace with a stable pseudonym (salted hash with a secret salt that is never exported) only if per-person analysis is needed; keep department (consider suppressing groups smaller than a threshold, e.g. fewer than 5 people).
- **Free-text answers can contain names or other identifiers.** Removing the name field does not make the data anonymous; offer a review step or automatic flagging before any external sharing. Call it "de-identified", not "anonymous".
- Sending any export to an external AI service needs explicit company authorization first.
- Exports are admin-only, logged, and written to git-ignored locations.
