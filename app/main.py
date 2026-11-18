from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app import questionnaire
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.routes import api, pages
from app.security import RequestProtectionMiddleware

APP_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None, *, create_tables: bool = False) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if create_tables:  # tests / quick local runs; real deployments use Alembic
            from app.db import Base
            import app.models  # noqa: F401

            Base.metadata.create_all(engine)
        with session_factory() as session:
            questionnaire.sync_versions(session, settings.questionnaire_dir)
            questionnaire.get_active(session, settings.active_questionnaire_version)
        yield
        engine.dispose()

    app = FastAPI(title="MIK | Process Insights", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)
    app.add_middleware(
        RequestProtectionMiddleware,
        allowed_origins=settings.allowed_origins,
        max_body_bytes=settings.max_json_body_bytes,
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz(request: Request):
        """Liveness + database check (used by Docker healthchecks). Never returns details."""
        try:
            with request.app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - report only the type, never connection details
            logging.getLogger("app").warning("health check failed: %s", type(exc).__name__)
            return JSONResponse({"status": "error"}, status_code=503)
        return {"status": "ok"}

    return app

