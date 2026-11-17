from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import questionnaire
from app.validation import date_window, fmt_date, today_local

router = APIRouter()

MONTHS_BG = [
    "януари", "февруари", "март", "април", "май", "юни",
    "юли", "август", "септември", "октомври", "ноември", "декември",
]


def bg_date(d) -> str:
    return f"{d.day} {MONTHS_BG[d.month - 1]} {d.year} г."


def backdate_hint(days: int) -> str:
    if days <= 0:
        return ""
    return f"Може да изберете до {days} {'ден' if days == 1 else 'дни'} назад."


@router.get("/", response_class=HTMLResponse)
def form_page(request: Request):
    s = request.app.state
    with s.session_factory() as session:
        definition = questionnaire.get_active(session, s.settings.active_questionnaire_version)
    today = today_local(s.settings.timezone)  # Europe/Sofia, never the browser clock
    earliest, _ = date_window(today, s.settings.max_backdate_days)
    picker = {
        "today": today.isoformat(),
        "min": earliest.isoformat(),
        "today_display": fmt_date(today),
        "hint": backdate_hint(s.settings.max_backdate_days),
    }
    return s.templates.TemplateResponse(
        request,
        "form.html",
        {"q": definition, "today_label": bg_date(today), "picker": picker},
    )
