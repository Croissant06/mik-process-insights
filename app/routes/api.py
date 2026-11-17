from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import questionnaire
from app.models import Submission
from app.validation import today_local, validate_submission

router = APIRouter(prefix="/api")


@router.get("/questionnaire")
def get_questionnaire(request: Request):
    s = request.app.state
    with s.session_factory() as session:
        return questionnaire.get_active(session, s.settings.active_questionnaire_version)


@router.post("/submissions")
async def create_submission(request: Request):
    s = request.app.state
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"errors": {"_form": "Невалидна заявка."}}, status_code=400)

    version = payload.get("questionnaire_version") if isinstance(payload, dict) else None
    with s.session_factory() as session:
        definition = questionnaire.get_version(session, version) if isinstance(version, int) else None
        if definition is None:
            return JSONResponse(
                {"errors": {"_form": "Формулярът е остарял. Моля, презаредете страницата."}},
                status_code=422,
            )
        today = today_local(s.settings.timezone)
        clean, errors = validate_submission(
            definition, payload, today=today, max_backdate_days=s.settings.max_backdate_days
        )
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        row = Submission(
            questionnaire_version=version,
            submitted_at=datetime.now(timezone.utc),
            **clean,
        )
        session.add(row)
        session.commit()
        return JSONResponse({"id": row.id}, status_code=201)
