"""Adapter cache wiring. Provider bodies here are SYNTHETIC, shaped like the real responses,
and exist only to count HTTP calls. The HTTP client and the store are test doubles."""

import json
from datetime import datetime, timedelta, timezone

from app.core.addresses import normalize_address
from app.providers.alchemy import AlchemyClient
from app.providers.cache import CacheHit
from app.providers.etherscan import EtherscanClient
from app.providers.goplus import GoPlusClient

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
KEY = "TEST-KEY-VALUE-12345"


class FakeResp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return FakeResp(self.body)

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        return FakeResp(self.body)


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.puts = []

    def get(self, key):
        return self.rows.get(key)

    def put(self, key, provider, status, raw, operation, fetched_at=None):
        self.puts.append({"key": key, "status": status, "operation": operation})
        if status not in ("ok", "not_found"):
            return False
        now = datetime.now(timezone.utc)
        self.rows[key] = CacheHit(status == "ok", raw, fetched_at or now, now + timedelta(hours=1))
        return True


def _etherscan(body, store):
    http = FakeHttp(body)
    client = EtherscanClient(
        KEY, http=http, requests_per_second=1000.0, max_attempts=1, sleep=lambda s: None, cache=store
    )
    return client, http


def _source_body(source_code):
    return {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "SourceCode": source_code,
                "ABI": "[]" if source_code else "Contract source code not verified",
                "ContractName": "A" if source_code else "",
                "CompilerVersion": "v0.8.0" if source_code else "",
                "Proxy": "0",
                "Implementation": "",
            }
        ],
    }


def test_etherscan_second_lookup_comes_from_cache_with_the_original_time():
    store = MemoryStore()
    client, http = _etherscan(_source_body("contract A {}"), store)
    first = client.get_contract_source(1, USDC)
    second = client.get_contract_source(1, USDC)
    assert first.status == second.status == "ok"
    assert http.calls == 1
    assert second.fetched_at == first.fetched_at
    assert second.data == first.data
    assert [p["operation"] for p in store.puts] == ["contract_source"]


def test_etherscan_unverified_answer_gets_the_short_ttl_class():
    store = MemoryStore()
    client, _ = _etherscan(_source_body(""), store)
    assert client.get_contract_source(1, USDC).status == "ok"
    assert [p["operation"] for p in store.puts] == ["contract_source_unverified"]


def test_etherscan_failure_is_never_stored():
    store = MemoryStore()
    body = {"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
    client, http = _etherscan(body, store)
    assert client.get_contract_source(1, USDC).status == "rate_limited"
    assert client.get_contract_source(1, USDC).status == "rate_limited"
    assert http.calls == 2
    assert store.puts == [] and store.rows == {}


def test_api_key_never_appears_in_a_cache_key_or_payload():
    store = MemoryStore()
    client, _ = _etherscan(_source_body("contract A {}"), store)
    client.get_contract_source(1, USDC)
    assert store.rows
    for k, hit in store.rows.items():
        assert KEY not in k and KEY not in json.dumps(hit.raw)


def test_alchemy_code_and_storage_are_cached_but_eth_call_is_not():
    store = MemoryStore()
    http = FakeHttp({"jsonrpc": "2.0", "id": 1, "result": "0x"})
    client = AlchemyClient(
        KEY, http=http, requests_per_second=1000.0, max_attempts=1, sleep=lambda s: None, cache=store
    )
    a = client.get_code(1, USDC)
    b = client.get_code(1, USDC)
    assert http.calls == 1 and b.data == "0x" and b.fetched_at == a.fetched_at
    slot = "0x" + "0" * 64
    client.get_storage_at(1, USDC, slot)
    client.get_storage_at(1, USDC, slot)
    assert http.calls == 2
    client.eth_call(1, USDC, "0x5c60da1b")
    client.eth_call(1, USDC, "0x5c60da1b")
    assert http.calls == 4
    assert {p["operation"] for p in store.puts} == {"code", "storage"}
    assert all(KEY not in k for k in store.rows)


def test_goplus_token_is_cached_and_an_empty_result_is_not():
    addr = normalize_address(USDC)
    store = MemoryStore()
    body = {
        "code": 1,
        "message": "OK",
        "result": {addr: {"token_name": "SyntheticToken", "token_symbol": "SYN", "is_open_source": "1"}},
    }
    http = FakeHttp(body)
    client = GoPlusClient(http=http, requests_per_second=1000.0, max_attempts=1, sleep=lambda s: None, cache=store)
    a = client.token_security(1, USDC)
    b = client.token_security(1, USDC)
    assert a.status == b.status == "ok" and http.calls == 1
    assert b.fetched_at == a.fetched_at and b.data == a.data

    empty_store = MemoryStore()
    empty_http = FakeHttp({"code": 1, "message": "OK", "result": {}})
    empty = GoPlusClient(
        http=empty_http, requests_per_second=1000.0, max_attempts=1, sleep=lambda s: None, cache=empty_store
    )
    assert empty.token_security(1, USDC).status == "not_found"
    assert empty.token_security(1, USDC).status == "not_found"
    assert empty_http.calls == 2 and empty_store.puts == []
