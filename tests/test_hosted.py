import pytest

from app.config import ConfigError, Settings
from app.questionnaire import QuestionnaireError
from tests.conftest import TEST_DB, write_version


def test_hosted_rejects_sqlite_and_insecure_config():
    with pytest.raises(ConfigError, match="PostgreSQL"):
        Settings(database_url="sqlite://", environment="production")
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        Settings(database_url="postgresql+psycopg://localhost/mik_test", environment="staging")
    with pytest.raises(ConfigError, match="HTTPS origin"):
        Settings(database_url="postgresql+psycopg://localhost/mik_test", environment="production", cookie_secure=True)


@pytest.mark.skipif(not TEST_DB, reason="Hosted mode uses PostgreSQL")
def test_production_refuses_draft_startup_and_historical_draft_submissions(qdir, make_client, valid_payload):
    settings = {"environment": "production", "cookie_secure": True, "public_origin": "https://reports.example.com"}
    with pytest.raises(QuestionnaireError, match="approved questionnaire"):
        make_client(**settings)

    def approve(definition):
        definition["status"] = "approved"
        definition["departments"]["placeholder"] = False

    write_version(qdir, 2, approve)
    client = make_client(**settings)
    report = valid_payload(client)
    origin = {"origin": settings["public_origin"]}
    assert client.post("/api/submissions", json=report, headers=origin).status_code == 422
    report["questionnaire_version"] = 2
    assert client.post("/api/submissions", json=report).status_code == 403
    assert client.post("/api/submissions", json=report, headers=origin).status_code == 201


def test_repo_questionnaires_draft_snapshot_kept_and_v3_approved():
    import yaml
    from pathlib import Path

    from app.questionnaire import is_approved

    d = Path(__file__).resolve().parent.parent / "questionnaire"
    v2, v3 = (yaml.safe_load((d / f"daily_report.v{n}.yaml").read_text(encoding="utf-8")) for n in (2, 3))
    assert v2["status"] == "draft" and not is_approved(v2)
    assert v3["status"] == "approved" and is_approved(v3) and v3["attachments"] is True
    strip = lambda x: {k: v for k, v in x.items() if k not in ("version", "status")}  # noqa: E731
    assert strip(v2) == strip(v3)  # same content, only version/status differ
    labels = [o["label"] for o in v3["departments"]["options"]]
    assert labels == ["Офис-администрация", "CAD/CAM", "Кроялен участък", "Шевен участък / Производство",
                      "Довършителен участък", "Склад и опаковка"]
