from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import questionnaire
from app.validation import allowed_dates, today_local

router = APIRouter()

MONTHS_BG = [
    "януари", "февруари", "март", "април", "май", "юни",
    "юли", "август", "септември", "октомври", "ноември", "декември",
]


def bg_date(d) -> str:
    return f"{d.day} {MONTHS_BG[d.month - 1]} {d.year} г."


@router.get("/", response_class=HTMLResponse)
def form_page(request: Request):
    s = request.app.state
    with s.session_factory() as session:
        definition = questionnaire.get_active(session, s.settings.active_questionnaire_version)
    today = today_local(s.settings.timezone)
    labels = ["Днес", "Вчера"]
    date_options = [
        {
            "value": d.isoformat(),
            "label": f"{labels[i] if i < len(labels) else 'Преди ' + str(i) + ' дни'}, {d.day} {MONTHS_BG[d.month - 1]}",
        }
        for i, d in enumerate(allowed_dates(today, s.settings.max_backdate_days))
    ]
    return s.templates.TemplateResponse(
        request,
        "form.html",
        {"q": definition, "today_label": bg_date(today), "date_options": date_options},
    )
