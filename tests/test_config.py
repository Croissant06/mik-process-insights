"""Production-mode configuration guards for the admin panel (HTTPS cookies, exact trusted origins)."""
import pytest

from app.config import ConfigError, Settings

BASE = {"DATABASE_URL": "postgresql+psycopg://a:b@h:1/d"}


def _env(monkeypatch, **env):
    for k in ("APP_ENV", "COOKIE_SECURE", "ALLOWED_ORIGINS", "DATABASE_URL", "POSTGRES_USER", "POSTGRES_DB"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {**BASE, **env}.items():
        monkeypatch.setenv(k, v)


def test_hosted_needs_exact_https_public_origin(monkeypatch):
    _env(monkeypatch, APP_ENV="production")
    with pytest.raises(ConfigError, match="PUBLIC_ORIGIN"):
        Settings.from_env()
    _env(monkeypatch, APP_ENV="production", PUBLIC_ORIGIN="http://reports.example.com")
    with pytest.raises(ConfigError, match="PUBLIC_ORIGIN"):
        Settings.from_env()
    _env(monkeypatch, APP_ENV="production", PUBLIC_ORIGIN="https://reports.example.com/",
         ATTACHMENT_SCAN_HOST="scanner")
    s = Settings.from_env()
    assert s.cookie_secure and s.public_origin == "https://reports.example.com"


def test_other_non_dev_envs_need_https_origins(monkeypatch):
    _env(monkeypatch, APP_ENV="preview")
    with pytest.raises(ConfigError, match="PUBLIC_ORIGIN"):
        Settings.from_env()
    _env(monkeypatch, APP_ENV="preview", ALLOWED_ORIGINS="http://x.example.com")
    with pytest.raises(ConfigError, match="https"):
        Settings.from_env()
    _env(monkeypatch, APP_ENV="preview", ALLOWED_ORIGINS="https://x.example.com")
    assert Settings.from_env().allowed_origins == ("https://x.example.com",)


def test_production_refuses_insecure_cookies(monkeypatch):
    _env(monkeypatch, APP_ENV="production", COOKIE_SECURE="0", PUBLIC_ORIGIN="https://reports.example.com")
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        Settings.from_env()


def test_unset_app_env_is_treated_as_production(monkeypatch):
    _env(monkeypatch)
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_dev_stays_easy(monkeypatch):
    _env(monkeypatch, APP_ENV="development")
    s = Settings.from_env()
    assert s.cookie_secure is False and s.allowed_origins == ()
