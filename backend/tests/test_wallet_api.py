"""Wallet API tests. Provider data is SYNTHETIC (fakes with a fake address); the database and
the OFAC address in the last tests are real."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.providers_dep import Providers, get_providers
from app.db.session import get_engine
from app.main import app
from app.providers.base import ProviderResult

SUBJECT = "0x" + "a" * 40
CALLS = {"history": 0}


class FakeHistory:
    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        CALLS["history"] += 1
        return ProviderResult("ok", "etherscan", [])

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return ProviderResult("ok", "etherscan", [])


class FakeRpc:
    def __init__(self, code="0x"):
        self.code = code

    def get_code(self, chain_id, address):
        return ProviderResult("ok", "alchemy", self.code)


class Unused:
    def __getattr__(self, name):
        raise AssertionError(f"{name} should not be called for a plain account")


class FakeGoPlus:
    def address_security(self, chain_id, address):
        return ProviderResult(
            "ok", "goplus", SimpleNamespace(flags={"phishing_activities": False}, malicious_contracts_created=0)
        )

    def token_security(self, chain_id, address):
        raise AssertionError("token_security should not be called for a plain account")


def _install(code="0x"):
    app.dependency_overrides[get_providers] = lambda: Providers(
        history=FakeHistory(), rpc=FakeRpc(code), explorer=Unused(), goplus=FakeGoPlus()
    )


def _clean(*keys):
    with get_engine().begin() as conn:
        for k in keys:
            conn.execute(text("DELETE FROM analysis_reports WHERE subject_key = :k"), {"k": k})


@pytest.fixture
def client():
    CALLS["history"] = 0
    _install()
    _clean(SUBJECT)
    yield TestClient(app)
    app.dependency_overrides.pop(get_providers, None)
    _clean(SUBJECT)


def test_analyze_requires_a_token(client):
    r = client.post("/v1/wallets/analyze", json={"chain_id": 1, "address": SUBJECT})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_invalid_address_uses_the_error_envelope_and_does_not_echo_input(client, auth_headers):
    r = client.post("/v1/wallets/analyze", json={"chain_id": 1, "address": "0xnothex"}, headers=auth_headers)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request" and "address" in err["message"]
    assert "0xnothex" not in r.text


def test_unsupported_chain_is_rejected(client, auth_headers):
    r = client.post("/v1/wallets/analyze", json={"chain_id": 999999, "address": SUBJECT}, headers=auth_headers)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_chain"


def test_second_call_is_served_from_the_stored_report(client, auth_headers):
    body = {"chain_id": 1, "address": SUBJECT}
    first = client.post("/v1/wallets/analyze", json=body, headers=auth_headers)
    assert first.status_code == 200
    calls_after_first = CALLS["history"]
    assert calls_after_first > 0
    second = client.post("/v1/wallets/analyze", json=body, headers=auth_headers)
    assert second.status_code == 200
    assert CALLS["history"] == calls_after_first  # providers were not called again
    assert second.json()["report_id"] == first.json()["report_id"]


def test_expired_stored_report_is_recomputed(client, auth_headers):
    body = {"chain_id": 1, "address": SUBJECT}
    first = client.post("/v1/wallets/analyze", json=body, headers=auth_headers).json()
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE analysis_reports SET expires_at = now() - interval '1 minute' WHERE subject_key = :k"),
            {"k": SUBJECT},
        )
    second = client.post("/v1/wallets/analyze", json=body, headers=auth_headers).json()
    assert second["report_id"] != first["report_id"]


def test_lookup_reports_address_type_and_dedupes(client, auth_headers):
    r = client.post(
        "/v1/addresses/lookup",
        json={"chain_id": 1, "addresses": [SUBJECT, SUBJECT]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["address_type"] == "eoa"
    assert results[0]["status"] in ("checked", "unavailable")


def test_lookup_marks_code_as_contract(client, auth_headers):
    _install(code="0x6080604052")
    r = client.post("/v1/addresses/lookup", json={"chain_id": 1, "addresses": [SUBJECT]}, headers=auth_headers)
    assert r.json()["results"][0]["address_type"] == "contract"


def _real_ofac_address():
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT e.address FROM intel_entries e JOIN intel_sources s ON s.id = e.source_id "
                "WHERE s.name = 'ofac_sdn' LIMIT 1"
            )
        ).first()
    return row[0] if row else None


def test_real_ofac_address_is_critical_and_listed_in_lookup(client, auth_headers):
    addr = _real_ofac_address()
    if addr is None:
        pytest.skip("no OFAC rows loaded")
    _clean(addr)
    try:
        lk = client.post("/v1/addresses/lookup", json={"chain_id": 1, "addresses": [addr]}, headers=auth_headers)
        hits = lk.json()["results"][0]["intel_hits"]
        assert any(h["source"] == "ofac_sdn" for h in hits)

        an = client.post("/v1/wallets/analyze", json={"chain_id": 1, "address": addr}, headers=auth_headers)
        report = an.json()
        assert report["risk_level"] == "CRITICAL"
        assert any(e["id"].startswith("intel.ofac_sdn") for e in report["evidence"])
    finally:
        _clean(addr)
