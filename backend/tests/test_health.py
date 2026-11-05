from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db import session as db_session
from app.db.session import check_database, get_engine
from app.main import app, create_app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "ChainGuard API"
    assert "timestamp" in body


def test_config_status_hides_secret_values(monkeypatch, auth_headers):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "super-secret-value")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        r = c.get("/v1/config/status", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["etherscan_configured"] is True
        assert "super-secret-value" not in r.text
    finally:
        get_settings.cache_clear()

def test_health_reports_database_field():
    body = client.get("/health").json()
    assert body["database"] in {"ok", "unavailable", "not_configured"}


def test_health_database_unavailable_is_explicit(monkeypatch):
    # Real connection attempt to a closed local port. Nothing is mocked.
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        c = TestClient(create_app())
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["database"] == "unavailable"
        assert "nopass" not in r.text
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()


def test_database_not_configured_is_explicit(monkeypatch):
    monkeypatch.setattr(db_session, "get_settings", lambda: Settings(_env_file=None))
    get_engine.cache_clear()
    try:
        assert check_database() == "not_configured"
    finally:
        get_engine.cache_clear()
