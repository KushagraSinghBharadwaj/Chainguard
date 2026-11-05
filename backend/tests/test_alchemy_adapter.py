import json
import logging

import httpx
import pytest

from app.providers.alchemy import AlchemyClient
from app.providers.etherscan import Throttle

# FIXTURES: synthetic JSON-RPC responses for deterministic parsing/failure tests only.
# Real-provider behavior is verified by tests/test_alchemy_live.py (pytest --live).

KEY = "test-key-not-real"
ADDR = "0x" + "a" * 40
OTHER = "0x" + "b" * 40


def rpc_ok(result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


def rpc_err(code, message):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": message}})


def make_client(*steps, **kw):
    state = {"calls": 0, "sleeps": [], "bodies": []}

    def handler(request):
        i = min(state["calls"], len(steps) - 1)
        state["calls"] += 1
        state["bodies"].append(json.loads(request.content))
        step = steps[i]
        if isinstance(step, Exception):
            raise step
        return step

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = AlchemyClient(KEY, http=http, sleep=state["sleeps"].append, throttle=Throttle(1000.0), **kw)
    return client, state


def test_contract_code_is_returned():
    c, _ = make_client(rpc_ok("0x6080604052"))
    r = c.get_code(1, ADDR)
    assert r.status == "ok" and r.data == "0x6080604052"


def test_wallet_without_code_is_an_explicit_0x():
    c, _ = make_client(rpc_ok("0x"))
    r = c.get_code(1, ADDR)
    assert r.status == "ok" and r.data == "0x"


def test_eth_call_returns_data():
    c, _ = make_client(rpc_ok("0x" + "00" * 31 + "01"))
    r = c.eth_call(1, ADDR, "0x95d89b41")
    assert r.status == "ok" and r.data.reverted is False and r.data.return_data.endswith("01")


def test_eth_call_revert_is_a_result_not_a_failure():
    c, state = make_client(rpc_err(3, "execution reverted: insufficient balance"))
    r = c.eth_call(1, ADDR, "0xa9059cbb", from_address=OTHER)
    assert r.status == "ok" and r.data.reverted is True and r.data.return_data is None
    assert state["calls"] == 1


def test_revert_error_on_get_code_is_unavailable():
    c, _ = make_client(rpc_err(3, "execution reverted"))
    r = c.get_code(1, ADDR)
    assert r.status == "unavailable" and r.detail == "provider_error" and r.data is None


def test_rate_limit_then_success_retries():
    c, state = make_client(httpx.Response(429), rpc_ok("0x"))
    r = c.get_code(1, ADDR)
    assert r.status == "ok" and state["calls"] == 2
    assert len(state["sleeps"]) == 1 and state["sleeps"][0] >= 1.0


def test_persistent_rate_limit_is_rate_limited_not_empty():
    c, state = make_client(rpc_err(429, "exceeded its compute units per second capacity"))
    r = c.get_code(1, ADDR)
    assert r.status == "rate_limited" and r.data is None and state["calls"] == 3


def test_auth_error_is_unavailable_and_never_retried():
    c, state = make_client(httpx.Response(401))
    r = c.get_code(1, ADDR)
    assert r.status == "unavailable" and r.detail == "auth_error" and state["calls"] == 1


def test_unsupported_chain_makes_no_request():
    c, state = make_client(rpc_ok("0x"))
    r = c.get_code(999999, ADDR)
    assert r.status == "unavailable" and r.detail == "unsupported_chain" and state["calls"] == 0


def test_non_hex_result_is_unexpected_shape():
    c, _ = make_client(rpc_ok("not-hex"))
    r = c.get_code(1, ADDR)
    assert r.status == "unavailable" and r.detail == "unexpected_shape" and r.data is None


def test_invalid_calldata_and_slot_are_rejected():
    c, state = make_client(rpc_ok("0x"))
    with pytest.raises(ValueError):
        c.eth_call(1, ADDR, "zzzz")
    with pytest.raises(ValueError):
        c.get_storage_at(1, ADDR, "0x" + "0" * 70)
    assert state["calls"] == 0


def test_request_shape_and_lowercase_address():
    c, state = make_client(rpc_ok("0x"))
    c.get_code(1, "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
    body = state["bodies"][0]
    assert body["method"] == "eth_getCode" and body["jsonrpc"] == "2.0"
    assert body["params"] == ["0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed", "latest"]


def test_storage_slot_is_returned():
    c, _ = make_client(rpc_ok("0x" + "00" * 32))
    r = c.get_storage_at(1, ADDR, "0x0")
    assert r.status == "ok" and len(r.data) == 66


def test_api_key_never_appears_in_results_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    c, _ = make_client(httpx.ConnectError("boom"))
    r = c.get_code(1, ADDR)
    assert r.status == "unavailable" and r.detail == "ConnectError"
    assert KEY not in repr(r) and KEY not in caplog.text
