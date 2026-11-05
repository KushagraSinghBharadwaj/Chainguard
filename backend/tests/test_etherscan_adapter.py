import httpx
import pytest

from app.providers.etherscan import EtherscanClient, Throttle

# FIXTURES: synthetic provider responses, used only to test parsing and failure handling
# deterministically. They live under backend/tests/ only and are never imported by product
# code. Real-provider behavior is verified by the live tests (pytest --live).

KEY = "test-key-not-real"
ADDR = "0x" + "a" * 40
OTHER = "0x" + "b" * 40
RATE_TEXT = "Max rate limit reached, please use API Key for higher rate limit"


def ok(result):
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": result})


def err(text):
    return httpx.Response(200, json={"status": "0", "message": "NOTOK", "result": text})


def tx_row(**over):
    row = {
        "blockNumber": "100", "timeStamp": "1600000000", "hash": "0x" + "1" * 64,
        "from": ADDR, "to": OTHER, "value": "1000", "gasUsed": "21000",
        "isError": "0", "input": "0xa9059cbb0000",
    }
    row.update(over)
    return row


def make_client(*steps, **kw):
    state = {"calls": 0, "sleeps": [], "queries": []}

    def handler(request):
        i = min(state["calls"], len(steps) - 1)
        state["calls"] += 1
        state["queries"].append(dict(request.url.params))
        step = steps[i]
        if isinstance(step, Exception):
            raise step
        return step

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = EtherscanClient(
        KEY, http=http, sleep=state["sleeps"].append, throttle=Throttle(1000.0), **kw
    )
    return client, state


def test_transactions_are_parsed():
    c, _ = make_client(ok([tx_row(), tx_row(to="", isError="1", input="0x")]))
    r = c.get_transactions(1, ADDR)
    assert r.status == "ok" and len(r.data) == 2
    first, second = r.data
    assert first.from_address == ADDR and first.to_address == OTHER
    assert first.value_wei == 1000 and first.input_selector == "0xa9059cbb"
    assert first.timestamp.tzinfo is not None and first.is_error is False
    assert second.to_address is None and second.is_error is True
    assert second.input_selector is None


def test_no_transactions_found_is_an_explicit_empty_result():
    body = {"status": "0", "message": "No transactions found", "result": []}
    c, _ = make_client(httpx.Response(200, json=body))
    r = c.get_transactions(1, ADDR)
    assert r.status == "ok" and r.data == [] and r.detail == "no_transactions"


def test_rate_limit_then_success_retries():
    c, state = make_client(err(RATE_TEXT), ok([tx_row()]))
    r = c.get_transactions(1, ADDR)
    assert r.status == "ok" and state["calls"] == 2
    assert len(state["sleeps"]) == 1 and state["sleeps"][0] >= 1.0


def test_persistent_rate_limit_is_rate_limited_not_empty():
    c, state = make_client(err(RATE_TEXT))
    r = c.get_transactions(1, ADDR)
    assert r.status == "rate_limited" and r.data is None
    assert state["calls"] == 3
    assert all(s >= 1.0 for s in state["sleeps"])


def test_invalid_api_key_is_unavailable_and_never_retried():
    c, state = make_client(err("Invalid API Key"))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "invalid_api_key"
    assert state["calls"] == 1


def test_too_many_invalid_key_attempts_is_never_retried():
    c, state = make_client(err("Too many invalid api key attempts, please try again later"))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "too_many_invalid_api_key_attempts"
    assert state["calls"] == 1


def test_http_500_is_retried_then_unavailable():
    c, state = make_client(httpx.Response(500))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "http_500"
    assert state["calls"] == 3 and state["sleeps"] == [0.5, 1.0]


def test_network_error_is_unavailable_with_class_name_only():
    c, state = make_client(httpx.ConnectError("boom"))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "ConnectError"
    assert state["calls"] == 3


def test_invalid_json_is_unavailable_without_retry():
    c, state = make_client(httpx.Response(200, content=b"<html>oops</html>"))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "invalid_json"
    assert state["calls"] == 1


def test_malformed_row_makes_the_whole_result_unavailable():
    bad = tx_row()
    del bad["isError"]
    c, _ = make_client(ok([tx_row(), bad]))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "unexpected_shape" and r.data is None


def test_unknown_error_is_not_treated_as_empty():
    c, _ = make_client(err("Something unexpected happened"))
    r = c.get_transactions(1, ADDR)
    assert r.status == "unavailable" and r.detail == "provider_error" and r.data is None


def test_throttle_spaces_calls():
    sleeps = []
    t = Throttle(3.0, clock=lambda: 0.0, sleep=sleeps.append)
    for _ in range(4):
        t.wait()
    assert [round(s, 3) for s in sleeps] == [0.333, 0.667, 1.0]


def test_token_transfers_are_parsed():
    row = {
        "blockNumber": "5", "timeStamp": "1600000000", "hash": "0x" + "2" * 64,
        "from": ADDR, "to": OTHER, "contractAddress": "0x" + "c" * 40,
        "tokenSymbol": "USDC", "tokenDecimal": "6", "value": "2500000",
    }
    c, _ = make_client(ok([row]))
    r = c.get_token_transfers(1, ADDR)
    t = r.data[0]
    assert r.status == "ok" and t.token_symbol == "USDC" and t.token_decimals == 6
    assert t.value_raw == 2500000 and t.contract_address == "0x" + "c" * 40


def test_verified_contract_is_parsed():
    row = {
        "SourceCode": "contract X {}", "ABI": "[{}]", "ContractName": "X",
        "CompilerVersion": "v0.8.0", "Proxy": "1", "Implementation": OTHER,
    }
    c, _ = make_client(ok([row]))
    r = c.get_contract_source(1, ADDR)
    d = r.data
    assert r.status == "ok" and d.verified and d.contract_name == "X"
    assert d.abi_json == "[{}]" and d.is_proxy and d.implementation == OTHER


def test_unverified_contract_is_not_reported_verified():
    # Assumed shape for unverified contracts; the live test checks it against the real API.
    row = {
        "SourceCode": "", "ABI": "Contract source code not verified", "ContractName": "",
        "CompilerVersion": "", "Proxy": "0", "Implementation": "",
    }
    c, _ = make_client(ok([row]))
    r = c.get_contract_source(1, ADDR)
    assert r.status == "ok" and r.data.verified is False and r.data.abi_json is None


def test_request_parameters_and_lowercase_address():
    c, state = make_client(ok([]))
    c.get_transactions(1, "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
    q = state["queries"][0]
    assert q["chainid"] == "1" and q["module"] == "account" and q["action"] == "txlist"
    assert q["address"] == "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed"
    assert q["sort"] == "desc" and q["page"] == "1" and q["offset"] == "100"
    assert q["apikey"] == KEY


def test_api_key_never_appears_in_results():
    c, _ = make_client(err("Invalid API Key"), httpx.ConnectError("boom"))
    r1 = c.get_transactions(1, ADDR)
    c2, _ = make_client(httpx.ConnectError("boom"))
    r2 = c2.get_transactions(1, ADDR)
    assert KEY not in repr(r1) and KEY not in repr(r2)
