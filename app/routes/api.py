from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app import questionnaire
from app.attachments import InvalidAttachment, ScannerUnavailable, prepare_files
from app.models import Submission
from app.validation import today_local, validate_submission

router = APIRouter(prefix="/api")


@router.get("/questionnaire")
def get_questionnaire(request: Request):
    s = request.app.state
    with s.session_factory() as session:
        return questionnaire.get_active(session, s.settings.active_questionnaire_version)


@router.post("/submissions")
@router.post("/submissions/with-attachments")
async def create_submission(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"errors": {"_form": "Невалидна заявка."}}, status_code=400)
    return await run_in_threadpool(
        _save_submission, request.app.state, payload, request.url.path.endswith("/with-attachments")
    )


def _save_submission(s, payload, has_files: bool):
    version = payload.get("questionnaire_version") if isinstance(payload, dict) else None
    with s.session_factory() as session:
        definition = questionnaire.get_version(session, version) if type(version) is int else None
        if definition is None or (s.settings.environment == "production" and not questionnaire.is_approved(definition)):
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
        files = []
        if has_files:
            if definition.get("attachments") is not True:
                return JSONResponse({"errors": {"attachments": "Този отчет не приема файлове."}}, status_code=422)
            try:
                files = prepare_files(payload.get("attachments"), s.settings)
            except InvalidAttachment as exc:
                return JSONResponse({"errors": {"attachments": str(exc)}}, status_code=422)
            except ScannerUnavailable:
                return JSONResponse(
                    {"errors": {"attachments": "Проверката на файлове временно не е достъпна. Опитайте отново."}},
                    status_code=503,
                )
        elif payload.get("attachments"):
            return JSONResponse({"errors": {"_form": "Невалидна заявка за прикачване."}}, status_code=422)
        row = Submission(
            questionnaire_version=version,
            submitted_at=datetime.now(timezone.utc),
            **clean,
        )
        session.add(row)
        if files:
            session.flush()
            for attachment in files:
                attachment.submission_id = row.id
            session.add_all(files)
        session.commit()
        return JSONResponse({"id": row.id}, status_code=201)
