from fastapi.testclient import TestClient
from sqlalchemy import text
import pytest

from app.api.clients import register_limiter
from app.core.security import hash_token
from app.db.session import get_engine
from app.main import app

client = TestClient(app)
created: list[str] = []


@pytest.fixture(autouse=True)
def _isolate():
    register_limiter.reset()
    created.clear()
    yield
    with get_engine().begin() as conn:
        for cid in created:
            conn.execute(text("DELETE FROM client_tokens WHERE client_id = CAST(:c AS uuid)"), {"c": cid})
            conn.execute(text("DELETE FROM clients WHERE id = CAST(:c AS uuid)"), {"c": cid})
    register_limiter.reset()


def _register() -> dict:
    r = client.post("/v1/clients/register")
    assert r.status_code == 200, r.text
    body = r.json()
    created.append(body["client_id"])
    return body


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_stores_only_the_hash():
    body = _register()
    assert body["token"] and body["expires_at"]
    with get_engine().connect() as conn:
        q = text("SELECT count(*) FROM client_tokens WHERE token_hash = :t")
        assert conn.execute(q, {"t": body["token"]}).scalar() == 0
        assert conn.execute(q, {"t": hash_token(body["token"])}).scalar() == 1


def test_refresh_without_or_with_bad_token_is_401():
    r = client.post("/v1/clients/token/refresh")
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "unauthenticated" and err["request_id"]
    assert r.headers["www-authenticate"] == "Bearer"
    r = client.post("/v1/clients/token/refresh", headers=_bearer("not-a-real-token"))
    assert r.status_code == 401


def test_refresh_rotates_and_revokes_old_token():
    first = _register()
    r = client.post("/v1/clients/token/refresh", headers=_bearer(first["token"]))
    assert r.status_code == 200
    second = r.json()
    assert second["token"] != first["token"]
    assert second["client_id"] == first["client_id"]
    assert client.post("/v1/clients/token/refresh", headers=_bearer(first["token"])).status_code == 401
    assert client.post("/v1/clients/token/refresh", headers=_bearer(second["token"])).status_code == 200


def test_register_is_rate_limited_per_ip():
    for _ in range(5):
        _register()
    r = client.post("/v1/clients/register")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"


def test_revoked_client_is_rejected():
    body = _register()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE clients SET revoked_at = now() WHERE id = CAST(:c AS uuid)"), {"c": body["client_id"]})
    assert client.post("/v1/clients/token/refresh", headers=_bearer(body["token"])).status_code == 401


def test_expired_token_is_rejected():
    body = _register()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE client_tokens SET expires_at = now() - interval '1 minute' WHERE client_id = CAST(:c AS uuid)"), {"c": body["client_id"]})
    assert client.post("/v1/clients/token/refresh", headers=_bearer(body["token"])).status_code == 401
