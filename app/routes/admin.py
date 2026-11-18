"""Admin panel (read-only for now): login, report list with filters, report detail, logout.

Only people created with scripts/admin_users.py can sign in. Every page requires a valid server-side session.
"""
from __future__ import annotations

import hmac
from datetime import date
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import admin_auth as auth
from app import questionnaire
from app.models import QuestionnaireVersion, Submission

router = APIRouter(prefix="/admin")
PAGE_SIZE = 25
GENERIC_LOGIN_ERROR = "Грешно потребителско име или парола."


def _harden(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    # NOT "no-referrer": with it browsers send "Origin: null" on same-origin form posts, which the request-protection
    # middleware (correctly) refuses. "same-origin" keeps the referrer private from other sites.
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _page(request: Request, template: str, ctx: dict, status: int = 200):
    return _harden(request.app.state.templates.TemplateResponse(request, template, ctx, status_code=status))


def _redirect(url: str):
    return _harden(RedirectResponse(url, status_code=303))


def _set_cookie(request: Request, resp, token: str):
    resp.set_cookie(
        auth.COOKIE_NAME, token, httponly=True, samesite="strict", path="/admin",
        secure=request.app.state.settings.cookie_secure,
    )


def _clear_cookie(request: Request, resp):
    resp.delete_cookie(auth.COOKIE_NAME, path="/admin", httponly=True, samesite="strict",
                       secure=request.app.state.settings.cookie_secure)


async def _form(request: Request) -> dict[str, str]:
    raw = (await request.body()).decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True, max_num_fields=20).items()}


def _current(request: Request):
    """(user, session) or None. Uses its own DB session so handlers can open theirs."""
    with request.app.state.session_factory() as db:
        found = auth.load_session(db, request.cookies.get(auth.COOKIE_NAME))
        if not found:
            return None
        user, sess = found
        return {"id": user.id, "name": user.display_name}, {"csrf": sess.csrf_token}


def _client_key(request: Request, login: str) -> tuple[str, str]:
    ip = request.client.host if request.client else "?"
    return f"ip:{ip}", f"login:{login.strip().lower()[:64]}"


# ---- login / logout ---------------------------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if _current(request):
        return _redirect("/admin")
    return _page(request, "admin_login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    s = request.app.state
    form = await _form(request)
    login, password = form.get("login", "")[:64], form.get("password", "")[:256]
    ip_key, login_key = _client_key(request, login)
    throttle = s.login_throttle
    if throttle.locked_for(ip_key) or throttle.locked_for(login_key):
        with s.session_factory() as db:
            auth.audit(db, "login_throttled")
        return _page(request, "admin_login.html", {"error": "Твърде много опити. Опитайте по-късно."}, 429)

    with s.session_factory() as db:
        user = auth.get_by_login(db, login)
        ok = auth.verify_password(password, user.password_hash if user else auth.DUMMY_HASH)
        if ok and user and user.is_active:
            throttle.success(login_key)
            token, _ = auth.start_session(db, user)
            auth.audit(db, "login_ok", user.id)
            resp = _redirect("/admin")
            _set_cookie(request, resp, token)
            return resp
        throttle.failure(ip_key)
        throttle.failure(login_key)
        auth.audit(db, "login_failed", user.id if user else None)  # never the attempted name or password
    return _page(request, "admin_login.html", {"error": GENERIC_LOGIN_ERROR}, 401)


@router.post("/logout")
async def logout(request: Request):
    cur = _current(request)
    if not cur:
        return _redirect("/admin/login")
    user, sess = cur
    form = await _form(request)
    if not hmac.compare_digest(form.get("csrf", ""), sess["csrf"]):
        return _page(request, "admin_login.html", {"error": "Заявката е отказана."}, 403)
    with request.app.state.session_factory() as db:
        auth.end_session(db, request.cookies.get(auth.COOKIE_NAME))
        auth.audit(db, "logout", user["id"])
    resp = _redirect("/admin/login")
    _clear_cookie(request, resp)
    return resp


# ---- data views -------------------------------------------------------------------------------------------------

def _label_maps(db):
    """department code -> label and (question id) -> definition, merged over all stored versions (newest wins)."""
    depts: dict[str, str] = {}
    for qv in db.scalars(select(QuestionnaireVersion).order_by(QuestionnaireVersion.version)):
        for o in qv.definition.get("departments", {}).get("options", []):
            depts[o["code"]] = o["label"]
    return depts


def _parse_date(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw and len(raw) == 10 else None
    except ValueError:
        return None


def _local(dt, tz: str) -> str:
    return auth.aware(dt).astimezone(ZoneInfo(tz)).strftime("%d.%m.%Y %H:%M")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def report_list(request: Request):
    cur = _current(request)
    if not cur:
        return _redirect("/admin/login")
    user, sess = cur
    s = request.app.state
    q = request.query_params
    dept = (q.get("department") or "")[:64]
    d_from, d_to = _parse_date(q.get("from")), _parse_date(q.get("to"))
    try:
        version = int(q.get("version", ""))
    except ValueError:
        version = None
    try:
        page = max(1, int(q.get("page", "1")))
    except ValueError:
        page = 1

    stmt = select(Submission)
    if dept:
        stmt = stmt.where(Submission.department_code == dept)
    if d_from:
        stmt = stmt.where(Submission.work_date >= d_from)
    if d_to:
        stmt = stmt.where(Submission.work_date <= d_to)
    if version is not None:
        stmt = stmt.where(Submission.questionnaire_version == version)

    with s.session_factory() as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(
            stmt.order_by(Submission.submitted_at.desc()).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)
        ).all()
        depts = _label_maps(db)
        versions = [v for v in db.scalars(select(QuestionnaireVersion.version).order_by(QuestionnaireVersion.version))]
        auth.audit(db, "list_reports", user["id"], f"n={total}")
        items = [
            {
                "id": r.id, "work_date": r.work_date.strftime("%d.%m.%Y"), "submitted": _local(r.submitted_at, s.settings.timezone),
                "name": r.respondent_name or "", "department": depts.get(r.department_code, r.department_code),
                "version": r.questionnaire_version,
                "tasks": (r.answers.get("tasks") or "")[:90] if isinstance(r.answers, dict) else "",
            }
            for r in rows
        ]
    pages = max(1, -(-total // PAGE_SIZE))
    keep = {k: v for k, v in {"department": dept, "from": q.get("from") or "", "to": q.get("to") or "",
                              "version": q.get("version") or ""}.items() if v}
    from urllib.parse import urlencode

    return _page(request, "admin_list.html", {
        "user": user, "csrf": sess["csrf"], "items": items, "total": total, "page": min(page, pages), "pages": pages,
        "depts": depts, "versions": versions, "f": {"department": dept, "from": q.get("from") or "", "to": q.get("to") or "",
                                                      "version": q.get("version") or ""},
        "qs": urlencode(keep),
    })


@router.get("/reports/{sid}", response_class=HTMLResponse)
def report_detail(request: Request, sid: str):
    cur = _current(request)
    if not cur:
        return _redirect("/admin/login")
    user, sess = cur
    s = request.app.state
    with s.session_factory() as db:
        sub = db.get(Submission, sid[:36])
        if sub is None:
            return _page(request, "admin_report.html", {"user": user, "csrf": sess["csrf"], "r": None}, 404)
        definition = questionnaire.get_version(db, sub.questionnaire_version) or {}
        depts = _label_maps(db)
        answers = sub.answers if isinstance(sub.answers, dict) else {}
        rows = []
        for qdef in definition.get("questions", []):
            val = answers.get(qdef["id"])
            if qdef.get("type") == "multi_choice":
                opts = {o["code"]: o for o in qdef.get("options", [])}
                sel = (val or {}).get("selected", []) if isinstance(val, dict) else []
                texts = (val or {}).get("texts", {}) if isinstance(val, dict) else {}
                shown = [{"label": opts.get(c, {}).get("label", c), "text": texts.get(c, "")} for c in sel]
                rows.append({"label": qdef["label"], "choices": shown})
            else:
                rows.append({"label": qdef["label"], "text": val or ""})
        auth.audit(db, "view_report", user["id"], f"id={sub.id}")
        r = {
            "id": sub.id, "work_date": sub.work_date.strftime("%d.%m.%Y"), "submitted": _local(sub.submitted_at, s.settings.timezone),
            "name": sub.respondent_name or "", "department": depts.get(sub.department_code, sub.department_code),
            "version": sub.questionnaire_version, "rows": rows,
        }
    return _page(request, "admin_report.html", {"user": user, "csrf": sess["csrf"], "r": r})
