import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import deps
from app.core.clientip import client_ip
from app.core.ratelimit import TokenBucket
from app.main import app


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_burst_is_allowed_then_denied_with_retry_after():
    clock = FakeClock()
    b = TokenBucket(capacity=3, refill_per_second=1.0, clock=clock)
    assert [b.allow("k")[0] for _ in range(3)] == [True, True, True]
    allowed, retry = b.allow("k")
    assert allowed is False
    assert retry == pytest.approx(1.0)
    clock.advance(1.0)
    assert b.allow("k")[0] is True
    assert b.allow("k")[0] is False


def test_refill_never_exceeds_capacity():
    clock = FakeClock()
    b = TokenBucket(capacity=3, refill_per_second=1.0, clock=clock)
    b.allow("k")
    clock.advance(1000)
    assert [b.allow("k")[0] for _ in range(4)] == [True, True, True, False]


def test_keys_are_independent():
    clock = FakeClock()
    b = TokenBucket(capacity=1, refill_per_second=1.0, clock=clock)
    assert b.allow("a")[0] is True
    assert b.allow("a")[0] is False
    assert b.allow("b")[0] is True


def test_stale_keys_are_evicted_when_over_max_keys():
    clock = FakeClock()
    b = TokenBucket(capacity=1, refill_per_second=1.0, max_keys=2, clock=clock)
    for key in ("a", "b", "c"):
        b.allow(key)
    clock.advance(5)
    b.allow("d")
    assert len(b._state) == 1


def _request(headers=None, client=("9.9.9.9", 1234)):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


def test_forwarded_header_is_ignored_by_default():
    req = _request({"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req) == "9.9.9.9"


def test_forwarded_header_uses_last_entry_when_trusted():
    req = _request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert client_ip(req, trust_proxy_headers=True) == "5.6.7.8"


def test_trusted_without_header_falls_back_to_socket_address():
    assert client_ip(_request(), trust_proxy_headers=True) == "9.9.9.9"


def test_unknown_when_no_client_address():
    assert client_ip(_request(client=None)) == "unknown"


def test_token_limit_returns_429_with_retry_after(auth_headers, monkeypatch):
    monkeypatch.setattr(deps, "token_limiter", TokenBucket(capacity=2, refill_per_second=1 / 60))
    c = TestClient(app)
    for _ in range(2):
        r = c.get("/v1/config/status", headers=auth_headers)
        assert r.status_code not in (401, 429)
    r = c.get("/v1/config/status", headers=auth_headers)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"


def test_ip_limit_returns_429_for_authenticated_requests(auth_headers, monkeypatch):
    monkeypatch.setattr(deps, "ip_limiter", TokenBucket(capacity=1, refill_per_second=1 / 60))
    c = TestClient(app)
    assert c.get("/v1/config/status", headers=auth_headers).status_code not in (401, 429)
    r = c.get("/v1/config/status", headers=auth_headers)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


def test_ip_limit_also_applies_to_unauthenticated_requests(monkeypatch):
    monkeypatch.setattr(deps, "ip_limiter", TokenBucket(capacity=2, refill_per_second=1 / 60))
    c = TestClient(app)
    assert c.get("/v1/config/status").status_code == 401
    assert c.get("/v1/config/status").status_code == 401
    r = c.get("/v1/config/status")
    assert r.status_code == 429
    assert "retry-after" in r.headers
