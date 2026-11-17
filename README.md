# MIK | Process Insights

Вътрешен уеб формуляр „Дневник на работните дейности“ за събиране на доказателства за реалните работни процеси в МИК-БГ (инструмент за откриване на процеси, не за оценка на служители).

Internal discovery tool: employees spend ~5 minutes a day describing tasks, repeated work and obstacles. **Development uses synthetic data only. Do not deploy publicly.** See `docs/PROJECT_STATUS.md` and `docs/DECISIONS.md`.

## Run locally (Docker)

```bash
cp .env.example .env            # edit the password if you like
docker compose up --build       # web on http://127.0.0.1:8000 (localhost only)
docker compose exec web python scripts/seed_synthetic.py --count 30   # optional synthetic data
```

Migrations run automatically on start (`alembic upgrade head`). Stop with `docker compose down` (add `-v` to wipe the database).

## Run tests

Tests use SQLite, no Docker needed:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

## Run without Docker (SQLite)

```bash
export DATABASE_URL=sqlite:///./local-dev.db
alembic upgrade head
uvicorn app.main:create_app --factory --reload
```

## Changing the questionnaire

Questions, answer options, departments and whether the name is required all live in `questionnaire/daily_report.vN.yaml`.
To change them: copy the latest file to `daily_report.v(N+1).yaml`, bump `version`, edit, restart.
The highest version becomes active; old versions are kept in the `questionnaire_versions` table so existing submissions stay interpretable.
A version already stored in the database cannot be edited (the app refuses to start) — always create a new one.
Set `respondent.name.required: false` to make the name optional.

## Layout

```
app/            FastAPI app (routes, models, validation, templates, static)
questionnaire/  versioned questionnaire definitions (YAML)
migrations/     Alembic migrations
scripts/        seed_synthetic.py
tests/          pytest suite
datasets/synthetic/  the only place datasets may be committed (synthetic only)
docs/           PROJECT_STATUS.md, DECISIONS.md, ADMIN_EXPORT_REQUIREMENTS.md (future)
```

## API

- `GET /` — the form · `GET /api/questionnaire` — active definition
- `POST /api/submissions` — JSON; `201 {id}` or `422 {errors}`. All validation is enforced on the backend.
- `GET /healthz`

Work dates are Europe/Sofia calendar days; the calendar picker defaults to today (server-side Sofia date). By default every past day (from 2020-01-01) is selectable; set `MAX_BACKDATE_DAYS` to a number to limit it (`0` = today only). Future dates are never allowed, and the backend enforces the window. Database timestamps are UTC.
