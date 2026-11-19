"""Load, check and version questionnaire definitions.

Definitions live in questionnaire/daily_report.vN.yaml and are copied (immutably)
into the `questionnaire_versions` table, so old submissions can always be
interpreted with the wording that employees actually saw.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.models import QuestionnaireVersion

QUESTION_TYPES = {"text", "textarea", "multi_choice"}
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Limits that mirror the database columns (see app/models.py). Configuration may be stricter, never looser,
# otherwise PostgreSQL would reject rows that validation accepted (HTTP 500).
NAME_COLUMN_MAX = 120
TEXT_ANSWER_MAX = 20000


class QuestionnaireError(Exception):
    pass


def is_approved(definition: dict) -> bool:
    return definition.get("status") == "approved" and definition.get("departments", {}).get("placeholder") is False


def checksum(definition: dict) -> str:
    blob = json.dumps(definition, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def check_definition(d: dict, source: str = "questionnaire") -> None:
    def fail(msg: str):
        raise QuestionnaireError(f"{source}: {msg}")

    if not isinstance(d, dict):
        fail("must be a mapping")
    if not isinstance(d.get("version"), int) or d["version"] < 1:
        fail("`version` must be a positive integer")
    for key in ("title", "respondent", "departments", "questions"):
        if key not in d:
            fail(f"missing `{key}`")
    resp = d["respondent"]
    for key in ("name", "department"):
        if key not in resp or "label" not in resp[key]:
            fail(f"respondent.{key}.label missing")
    name_max = resp["name"].get("max_length", NAME_COLUMN_MAX)
    if type(name_max) is not int or not 1 <= name_max <= NAME_COLUMN_MAX:
        fail(f"respondent.name.max_length must be an integer between 1 and {NAME_COLUMN_MAX} (database column limit)")
    if resp["department"].get("required", True) is not True:
        fail(
            "respondent.department.required must be true: the department column is NOT NULL. "
            "To allow optional departments, add a database migration first."
        )
    dept_codes = [o.get("code") for o in d["departments"].get("options", [])]
    if not dept_codes:
        fail("departments.options is empty")
    if len(set(dept_codes)) != len(dept_codes) or not all(CODE_RE.match(str(c)) for c in dept_codes):
        fail("department codes must be unique snake_case identifiers")
    ids: set[str] = set()
    for q in d["questions"]:
        qid = q.get("id")
        if not qid or not CODE_RE.match(str(qid)) or qid in ids:
            fail(f"question id {qid!r} missing, malformed or duplicated")
        ids.add(qid)
        if q.get("type") not in QUESTION_TYPES:
            fail(f"question {qid}: unknown type {q.get('type')!r}")
        if not q.get("label"):
            fail(f"question {qid}: label missing")
        if q["type"] == "multi_choice":
            codes = [o.get("code") for o in q.get("options", [])]
            if not codes or len(set(codes)) != len(codes) or not all(CODE_RE.match(str(c)) for c in codes):
                fail(f"question {qid}: options need unique snake_case codes")
        elif "max_length" in q and (type(q["max_length"]) is not int or not 1 <= q["max_length"] <= TEXT_ANSWER_MAX):
            fail(f"question {qid}: max_length must be an integer between 1 and {TEXT_ANSWER_MAX}")


def load_file(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        d = yaml.safe_load(fh)
    check_definition(d, path.name)
    return d


def load_directory(directory: Path) -> dict[int, dict]:
    found: dict[int, dict] = {}
    for path in sorted(Path(directory).glob("*.v*.yaml")):
        d = load_file(path)
        if d["version"] in found:
            raise QuestionnaireError(f"{path.name}: duplicate version {d['version']}")
        found[d["version"]] = d
    if not found:
        raise QuestionnaireError(f"no questionnaire files in {directory}")
    return found


def sync_versions(session: Session, directory: Path) -> None:
    """Insert new versions; refuse to start if a stored version was edited."""
    for version, d in load_directory(directory).items():
        row = session.get(QuestionnaireVersion, version)
        digest = checksum(d)
        if row is None:
            session.add(QuestionnaireVersion(version=version, definition=d, checksum=digest))
        elif row.checksum != digest:
            raise QuestionnaireError(
                f"version {version} already exists in the database with different content. "
                "Published versions are immutable - create a new version file instead."
            )
    session.commit()


def get_version(session: Session, version: int) -> dict | None:
    row = session.get(QuestionnaireVersion, version)
    return row.definition if row else None


def get_active(session: Session, forced: int | None = None) -> dict:
    if forced is not None:
        d = get_version(session, forced)
        if d is None:
            raise QuestionnaireError(f"ACTIVE_QUESTIONNAIRE_VERSION={forced} not found")
        return d
    row = (
        session.query(QuestionnaireVersion).order_by(QuestionnaireVersion.version.desc()).first()
    )
    if row is None:
        raise QuestionnaireError("no questionnaire versions loaded")
    return row.definition
