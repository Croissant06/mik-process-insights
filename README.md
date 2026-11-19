# MIK | Process Insights

Вътрешен уеб формуляр „Дневник на работните дейности“ за събиране на доказателства за реалните работни процеси в МИК-БГ (инструмент за откриване на процеси, не за оценка на служители).

Internal discovery tool: employees spend ~5 minutes a day describing tasks, repeated work and obstacles. **Development uses synthetic data only. Do not deploy publicly.** See `docs/PROJECT_STATUS.md` and `docs/DECISIONS.md`. **AI assistants (Claude, ChatGPT): read `docs/AI_HANDOFF.md` at the start of every session and update it after significant changes.**

## Run locally (Docker)

```bash
cp .env.example .env            # set POSTGRES_PASSWORD once (see "Database credentials")
docker compose up --build       # web on http://127.0.0.1:8000 (localhost only)
docker compose exec web python scripts/seed_synthetic.py --count 30   # optional synthetic data
```

Migrations run automatically on start (`alembic upgrade head`). `GET /healthz` checks the database and returns 503 if it is unreachable; Compose uses it as the web healthcheck.
Stop with `docker compose down`. **Never add `-v` unless you really want to delete the database** (it removes the `pgdata` volume).

An older `.env` that still contains `DATABASE_URL=...` keeps working: `DATABASE_URL` wins when set. No volume or schema change is needed.

## Admin panel (read-only)

Open **http://127.0.0.1:8000/admin**. Only people created with the script below can sign in (at most 4 active admins, one personal account each, no shared login). Passwords are typed at a hidden prompt, stored as scrypt hashes, never printed or logged.

```bash
docker compose exec web python scripts/admin_users.py create --login <login> --name "<display name>"
docker compose exec web python scripts/admin_users.py list
docker compose exec web python scripts/admin_users.py set-password --login <login>   # signs the person out everywhere
docker compose exec web python scripts/admin_users.py deactivate --login <login>
```

Sessions are stored in PostgreSQL (idle timeout 2 h, absolute 12 h), the cookie is `HttpOnly` + `SameSite=Strict`, five failed logins lock a login/IP for 15 minutes, and every sign-in, list and report view is written to `admin_audit`. Set `COOKIE_SECURE=1` whenever the site is served over HTTPS (it defaults to on outside `APP_ENV=dev`, where the app also refuses to start without `ALLOWED_ORIGINS=https://...` and with `COOKIE_SECURE=0`). Passwords use scrypt n=2^17 (128 MiB, ~0.4 s); older hashes are upgraded at the next sign-in. Reports can be filtered by department, date range and questionnaire version. Export is not built yet. Run `docker compose up --build` after pulling: the first start applies migration `0002` (new tables only, existing data untouched).

## Database credentials

- Write the password **once**, in `POSTGRES_PASSWORD`. The app builds its connection string from `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (host `db`), and escapes special characters for you.
- PostgreSQL only applies the password when the data volume is first created. Changing `.env` later does **not** change the password inside an existing database. To rotate it: `docker compose exec db psql -U <user> -c "ALTER USER <user> PASSWORD 'new'"`, then update `.env`, then `docker compose up -d`.
- `DATABASE_URL` (optional) overrides the parts above. Without any database setting the app refuses to start; the SQLite fallback exists only with `APP_ENV=dev` (or `development`/`test`).
- `.env` is gitignored. Never commit it.

## Run tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                 # fast, SQLite
```

The same suite also runs on PostgreSQL, with the schema built by the real Alembic migration, plus extra Postgres-only checks (`tests/test_postgres.py`). **The target database is wiped (public schema dropped) for every test**, so the runner refuses to start unless all three hold: the database name is exactly `mik_test`, the host is `localhost`, `127.0.0.1`, `::1` or `db-test`, and you opt in with `ALLOW_DESTRUCTIVE_TESTS=1` (see `tests/safety.py`). It also refuses connection-string parameters (e.g. `?host=`, `?dbname=`) and any URL that points at the same host/port/database as `DATABASE_URL`. `docker-compose.test.yml` sets all of this for its throw-away database.

```bash
# with Docker (throw-away database in memory, nothing persisted):
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.test.yml down

# or against any PostgreSQL you have:
ALLOW_DESTRUCTIVE_TESTS=1 TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mik_test python -m pytest
```

## Dependencies (locked)

Direct dependencies are in `requirements.in` / `requirements-dev.in`; the exact, hash-pinned versions are in `requirements.txt` / `requirements-dev.txt`. Docker installs only from the lock with `--require-hashes`. To update:

```bash
uv pip compile requirements.in -o requirements.txt --generate-hashes --universal --python-version 3.12
uv pip compile requirements-dev.in -o requirements-dev.txt --generate-hashes --universal --python-version 3.12
```

## Run without Docker (SQLite, development only)

```bash
export APP_ENV=dev DATABASE_URL=sqlite:///./local-dev.db
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
