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
