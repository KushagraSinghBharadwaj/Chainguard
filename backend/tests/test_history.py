from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.clients import register_limiter
from app.core.security import hash_token
from app.db.models import ClientToken
from app.db.session import get_engine
from app.main import app
from app.services import history_store

client = TestClient(app)


def _report(level="LOW"):
    return {
        "report_id": str(uuid4()),
        "chain_id": 1,
        "risk_level": level,
        "engine_version": "test-0",
        "summary": "test summary",
        "subject": {"type": "token", "key": "0x" + "ab" * 20},
    }


def _client_id(headers):
    token = headers["Authorization"].split(" ", 1)[1]
    with Session(get_engine()) as db:
        return db.execute(
            select(ClientToken.client_id).where(ClientToken.token_hash == hash_token(token))
        ).scalar_one()


def test_history_requires_auth():
    assert client.get("/v1/history").status_code == 401


def test_history_starts_empty(auth_headers):
    r = client.get("/v1/history", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_recorded_reports_are_listed_newest_first(auth_headers):
    cid = _client_id(auth_headers)
    with Session(get_engine()) as db:
        history_store.record(db, cid, _report("LOW"))
        history_store.record(db, cid, _report("HIGH"))
    items = client.get("/v1/history", headers=auth_headers).json()["items"]
    assert [i["risk_level"] for i in items] == ["HIGH", "LOW"]
    assert items[0]["subject_type"] == "token"


def test_history_is_private_per_client(auth_headers):
    cid = _client_id(auth_headers)
    with Session(get_engine()) as db:
        history_store.record(db, cid, _report("HIGH"))
    register_limiter.reset()
    other = client.post("/v1/clients/register").json()
    try:
        r = client.get("/v1/history", headers={"Authorization": f"Bearer {other['token']}"})
        assert r.json()["items"] == []
    finally:
        with get_engine().begin() as conn:
            p = {"c": other["client_id"]}
            conn.execute(text("DELETE FROM client_tokens WHERE client_id = CAST(:c AS uuid)"), p)
            conn.execute(text("DELETE FROM clients WHERE id = CAST(:c AS uuid)"), p)


def test_recording_never_raises():
    with Session(get_engine()) as db:
        history_store.record(db, uuid4(), {})  # malformed report
        history_store.record(db, uuid4(), _report())  # client does not exist


def test_limit_is_validated(auth_headers):
    r = client.get("/v1/history?limit=0", headers=auth_headers)
    assert r.status_code in (400, 422)
