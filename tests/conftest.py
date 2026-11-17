import copy
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

REAL_DIR = Path(__file__).resolve().parent.parent / "questionnaire"


@pytest.fixture
def qdir(tmp_path):
    d = tmp_path / "q"
    d.mkdir()
    (d / "daily_report.v1.yaml").write_text((REAL_DIR / "daily_report.v1.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return d


@pytest.fixture
def make_client(tmp_path, qdir):
    clients = []

    def _make(**overrides):
        settings = Settings(database_url=f"sqlite:///{tmp_path / 't.db'}", questionnaire_dir=qdir, **overrides)
        c = TestClient(create_app(settings, create_tables=True))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def write_version(qdir, version, mutate):
    d = yaml.safe_load((REAL_DIR / "daily_report.v1.yaml").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    d["version"] = version
    mutate(d)
    (qdir / f"daily_report.v{version}.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def valid_payload():
    from app.validation import today_local

    return lambda client: {
        "questionnaire_version": 1,
        "respondent_name": "Тест Потребител",
        "department": "dept_1",
        "work_date": today_local("Europe/Sofia").isoformat(),
        "answers": {
            "tasks": "Синтетична задача",
            "recurring": "Синтетична повтаряща се дейност, 30 мин.",
            "obstacles": {"selected": ["waiting"], "texts": {}},
            "obstacles_detail": "",
            "suggestions": "",
        },
    }
