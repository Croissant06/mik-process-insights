from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import questionnaire
from app.attachments import InvalidAttachment, ScannerUnavailable, prepare_files
from app.models import Submission
from app.validation import today_local, validate_submission

router = APIRouter(prefix="/api")
KEY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _payload_hash(version: int, clean: dict, raw_files) -> str:
    """Fingerprint of the validated report plus the (still base64) files, so a retry can be recognised cheaply."""
    files = [[f.get("name"), hashlib.sha256(str(f.get("data")).encode()).hexdigest()]
             for f in (raw_files if isinstance(raw_files, list) else []) if isinstance(f, dict)]
    blob = json.dumps({"v": version, "c": clean, "f": files}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


DUPLICATE_CONFLICT = "Този ключ за подаване вече е използван за друг отчет. Презаредете страницата и опитайте отново."
# A full upload is ~70 MiB of base64 JSON held in memory (plus decoded bytes), so only a few run at once.
_UPLOAD_SLOTS = asyncio.Semaphore(2)


@router.get("/questionnaire")
def get_questionnaire(request: Request):
    s = request.app.state
    with s.session_factory() as session:
        return questionnaire.get_active(session, s.settings.active_questionnaire_version)


@router.post("/submissions")
@router.post("/submissions/with-attachments")
async def create_submission(request: Request):
    if request.url.path.endswith("/with-attachments"):
        if _UPLOAD_SLOTS.locked():
            return JSONResponse({"errors": {"attachments": "Системата обработва други файлове. Опитайте след малко."}},
                                status_code=503, headers={"Retry-After": "10"})
        async with _UPLOAD_SLOTS:
            return await _handle(request)
    return await _handle(request)


async def _handle(request: Request):
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
        key = payload.get("idempotency_key")
        digest = None
        if key is not None:
            if not isinstance(key, str) or not KEY_RE.match(key):
                return JSONResponse({"errors": {"_form": "Невалидна заявка."}}, status_code=422)
            digest = _payload_hash(version, clean, payload.get("attachments") if has_files else None)
            known = session.scalar(select(Submission).where(Submission.idempotency_key == key))
            if known is not None:
                if known.payload_hash == digest:
                    return JSONResponse({"id": known.id, "duplicate": True}, status_code=200)
                return JSONResponse({"errors": {"_form": DUPLICATE_CONFLICT}}, status_code=409)
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
            idempotency_key=key, payload_hash=digest,
            **clean,
        )
        session.add(row)
        try:
            if files:
                session.flush()
                for attachment in files:
                    attachment.submission_id = row.id
                session.add_all(files)
            session.commit()
        except IntegrityError:  # a parallel retry with the same key won the race
            session.rollback()
            known = session.scalar(select(Submission).where(Submission.idempotency_key == key)) if key else None
            if known is None:
                raise
            if known.payload_hash == digest:
                return JSONResponse({"id": known.id, "duplicate": True}, status_code=200)
            return JSONResponse({"errors": {"_form": DUPLICATE_CONFLICT}}, status_code=409)
        return JSONResponse({"id": row.id}, status_code=201)
