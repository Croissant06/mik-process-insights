"""Backend validation of submissions. The browser is never trusted."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MSG = {
    "required": "Моля, попълнете това поле.",
    "choose": "Моля, изберете отговор.",
    "too_long": "Текстът е твърде дълъг (максимум {n} символа).",
    "bad_choice": "Невалиден избор.",
    "exclusive": "Този отговор не може да се комбинира с другите.",
    "need_text": "Моля, уточнете.",
    "bad_date": "Невалидна дата.",
    "date_range": "Изберете дата между {min} и {max}.",
    "bad_type": "Невалиден формат.",
}


def today_local(tz_name: str, now: datetime | None = None) -> date:
    tz = ZoneInfo(tz_name)
    return (now.astimezone(tz) if now else datetime.now(tz)).date()


# Sanity floor so a typo such as year 1926 is rejected even when backdating is unlimited.
EARLIEST_WORK_DATE = date(2020, 1, 1)


def date_window(today: date, max_backdate_days: int | None) -> tuple[date, date]:
    """Inclusive (earliest, latest) work date an employee may pick. Never in the future."""
    if max_backdate_days is None:
        return EARLIEST_WORK_DATE, today
    return max(EARLIEST_WORK_DATE, today - timedelta(days=max(0, max_backdate_days))), today


def fmt_date(d: date) -> str:
    """DD.MM.YYYY, the format shown to employees."""
    return d.strftime("%d.%m.%Y")


def _clean_text(value) -> str | None:
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    return _CONTROL.sub("", value).strip()


def _text(value, *, required: bool, max_length: int, errors: dict, key: str) -> str:
    cleaned = _clean_text(value)
    if cleaned is None:
        errors[key] = MSG["bad_type"]
        return ""
    if required and not cleaned:
        errors[key] = MSG["required"]
    elif len(cleaned) > max_length:
        errors[key] = MSG["too_long"].format(n=max_length)
    return cleaned


def _multi(q: dict, value, errors: dict) -> dict:
    qid = q["id"]
    if value is None:
        value = {}
    if not isinstance(value, dict):
        errors[qid] = MSG["bad_type"]
        return {"selected": [], "texts": {}}
    selected = value.get("selected", [])
    texts = value.get("texts", {}) or {}
    if not isinstance(selected, list) or not all(isinstance(s, str) for s in selected) or not isinstance(texts, dict):
        errors[qid] = MSG["bad_type"]
        return {"selected": [], "texts": {}}
    options = {o["code"]: o for o in q["options"]}
    if any(s not in options for s in selected):
        errors[qid] = MSG["bad_choice"]
        return {"selected": [], "texts": {}}
    selected = list(dict.fromkeys(selected))  # de-duplicate, keep order
    if q.get("required") and not selected:
        errors[qid] = MSG["choose"]
    exclusive = [c for c in selected if options[c].get("exclusive")]
    if exclusive and len(selected) > 1:
        errors[qid] = MSG["exclusive"]
    clean_texts: dict[str, str] = {}
    for code in selected:
        if options[code].get("allows_text"):
            t = _clean_text(texts.get(code))
            if not t:
                errors[f"{qid}.{code}"] = MSG["need_text"]
            elif len(t) > 300:
                errors[f"{qid}.{code}"] = MSG["too_long"].format(n=300)
            else:
                clean_texts[code] = t
    return {"selected": selected, "texts": clean_texts}


def validate_submission(
    definition: dict, payload: dict, *, today: date, max_backdate_days: int | None
) -> tuple[dict | None, dict[str, str]]:
    """Return (clean_data, errors). clean_data is None when errors is non-empty."""
    errors: dict[str, str] = {}
    if not isinstance(payload, dict):
        return None, {"_form": MSG["bad_type"]}

    # respondent name (required or optional per questionnaire)
    name_cfg = definition["respondent"]["name"]
    name = _text(
        payload.get("respondent_name"),
        required=bool(name_cfg.get("required", True)),
        max_length=int(name_cfg.get("max_length", 120)),
        errors=errors,
        key="respondent_name",
    )

    # department
    dept = payload.get("department")
    dept_codes = {o["code"] for o in definition["departments"]["options"]}
    if not isinstance(dept, str) or not dept:
        if definition["respondent"]["department"].get("required", True):
            errors["department"] = MSG["choose"]
        dept = None
    elif dept not in dept_codes:
        errors["department"] = MSG["bad_choice"]

    # work date (Europe/Sofia calendar day)
    work_date = None
    raw_date = payload.get("work_date")
    try:
        work_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
    except ValueError:
        work_date = None
    if work_date is None:
        errors["work_date"] = MSG["bad_date"]
    else:
        earliest, latest = date_window(today, max_backdate_days)
        if not earliest <= work_date <= latest:
            errors["work_date"] = MSG["date_range"].format(min=fmt_date(earliest), max=fmt_date(latest))

    # questions
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, dict):
        raw_answers = {}
    answers: dict = {}
    for q in definition["questions"]:
        qid = q["id"]
        raw = raw_answers.get(qid)
        if q["type"] == "multi_choice":
            answers[qid] = _multi(q, raw, errors)
        else:
            answers[qid] = _text(
                raw,
                required=bool(q.get("required")),
                max_length=int(q.get("max_length", 2000)),
                errors=errors,
                key=qid,
            )

    if errors:
        return None, errors
    return (
        {
            "respondent_name": name or None,
            "department_code": dept,
            "work_date": work_date,
            "answers": answers,
        },
        {},
    )
