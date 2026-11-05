from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app, create_app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "ChainGuard API"
    assert "timestamp" in body


def test_config_status_hides_secret_values(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "super-secret-value")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        r = c.get("/config/status")
        assert r.status_code == 200
        assert r.json()["etherscan_configured"] is True
        assert "super-secret-value" not in r.text
    finally:
        get_settings.cache_clear()