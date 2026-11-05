import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.clients import register_limiter
from app.db.session import get_engine
from app.main import app


@pytest.fixture
def auth_headers():
    """Registers a real client against the real database, then deletes it."""
    register_limiter.reset()
    body = TestClient(app).post("/v1/clients/register").json()
    yield {"Authorization": f"Bearer {body['token']}"}
    with get_engine().begin() as conn:
        params = {"c": body["client_id"]}
        conn.execute(text("DELETE FROM client_tokens WHERE client_id = CAST(:c AS uuid)"), params)
        conn.execute(text("DELETE FROM clients WHERE id = CAST(:c AS uuid)"), params)
    register_limiter.reset()
