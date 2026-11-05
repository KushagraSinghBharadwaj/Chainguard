import json
import pathlib

import httpx
import pytest

from app.providers.goplus import GoPlusClient

FIX = pathlib.Path(__file__).parent / "fixtures"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
OFAC_ADDR = "0x0330070fd38ec3bb94f58fa55d40368271e9e54a"
SCAM_ADDR = "0x000000002651a7206f8d7a23fe4410edf16dbec3"
CLEAN_ADDR = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


def make(responses):
    """responses: list of (status, bytes); the last one repeats. Fixture bodies are real
    recorded GoPlus responses; bare status/garbage bodies are synthetic transport faults."""
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        status, content = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, content=content)

    client = GoPlusClient(
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=1000.0,
        sleep=sleeps.append,
    )
    return client, calls, sleeps


def test_token_usdc_parsed():
    client, calls, _ = make([(200, fixture("goplus_token_usdc.json"))])
    r = client.token_security(1, USDC.upper().replace("0X", "0x"))
    assert r.status == "ok"
    t = r.data
    assert t.symbol == "USDC" and t.name == "USD Coin"
    assert t.is_proxy is True and t.is_honeypot is False and t.is_open_source is True
    assert t.buy_tax == 0.0 and t.sell_tax == 0.0
    assert t.holder_count == 9392500 and t.trust_list is True
    assert "owner_address" not in t.raw and "owner_address" not in t.fields_present
    assert "token_security/1" in str(calls[0].url)
    assert f"contract_addresses={USDC}" in str(calls[0].url)


def test_token_unknown_is_not_found():
    client, _, _ = make([(200, fixture("goplus_token_unknown.json"))])
    r = client.token_security(1, "0x" + "12" * 20)
    assert r.status == "not_found" and r.data is None


def test_address_ofac_listed_is_not_flagged_sanctioned_by_goplus():
    # Recorded finding: OFAC lists this address, GoPlus does not set 'sanctioned'.
    # Sources disagree, so each source must be reported separately.
    client, _, _ = make([(200, fixture("goplus_address_ofac.json"))])
    r = client.address_security(1, OFAC_ADDR)
    assert r.status == "ok"
    assert r.data.flags["sanctioned"] is False
    assert r.data.positive_flags() == ["stealing_attack"]
    assert r.data.data_sources == ("SlowMist",)


def test_address_scamsniffer_listed_is_flagged_with_sources():
    client, _, _ = make([(200, fixture("goplus_address_scamsniffer.json"))])
    r = client.address_security(1, SCAM_ADDR)
    assert r.status == "ok"
    assert "phishing_activities" in r.data.positive_flags()
    # GoPlus lists ScamSniffer among its own sources: not independent of our ScamSniffer table.
    assert "ScamSniffer" in r.data.data_sources


def test_address_clean_has_no_positive_flags():
    # Empty flags mean "not flagged by GoPlus", not "safe".
    client, _, _ = make([(200, fixture("goplus_address_clean.json"))])
    r = client.address_security(1, CLEAN_ADDR)
    assert r.status == "ok"
    assert r.data.positive_flags() == []
    assert r.data.flags["contract_address"] is True
    assert r.data.data_sources == ()


def test_unsupported_chain_code_is_unavailable():
    client, calls, _ = make([(200, fixture("goplus_error_chain.json"))])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "unsupported_chain"
    assert len(calls) == 1


def test_bad_address_code_5000_is_unavailable():
    client, _, _ = make([(200, fixture("goplus_error_badaddr.json"))])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "goplus_code_5000"


def test_http_429_then_success_retries():
    client, calls, sleeps = make([(429, b""), (200, fixture("goplus_token_usdc.json"))])
    r = client.token_security(1, USDC)
    assert r.status == "ok" and len(calls) == 2 and len(sleeps) == 1


def test_http_500_exhausts_attempts():
    client, calls, sleeps = make([(500, b"")])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "http_500"
    assert len(calls) == 3 and len(sleeps) == 2


def test_invalid_json():
    client, calls, _ = make([(200, b"not json")])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "invalid_json" and len(calls) == 1


def test_auth_error_not_retried():
    client, calls, _ = make([(403, b"")])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "auth_error" and len(calls) == 1


def test_unsupported_chain_makes_no_request():
    client, calls, _ = make([(200, b"{}")])
    r = client.token_security(137, USDC)
    assert r.status == "unavailable" and r.detail == "unsupported_chain" and len(calls) == 0


def test_invalid_address_makes_no_request():
    client, calls, _ = make([(200, b"{}")])
    with pytest.raises(Exception):
        client.token_security(1, "notanaddress")
    assert len(calls) == 0


def test_non_dict_result_is_unexpected_shape():
    body = json.dumps({"code": 1, "message": "OK", "result": []}).encode()
    client, _, _ = make([(200, body)])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "unexpected_shape"


def test_result_missing_requested_address_is_unexpected_shape():
    body = json.dumps({"code": 1, "message": "OK", "result": {"0x" + "ab" * 20: {"token_name": "X"}}}).encode()
    client, _, _ = make([(200, body)])
    r = client.token_security(1, USDC)
    assert r.status == "unavailable" and r.detail == "unexpected_shape"


def test_rate_limit_message_is_rate_limited():
    # Synthetic: the real GoPlus rate-limit code has not been observed, detection is by message.
    body = json.dumps({"code": 4029, "message": "Too many requests", "result": None}).encode()
    client, calls, sleeps = make([(200, body)])
    r = client.token_security(1, USDC)
    assert r.status == "rate_limited" and len(calls) == 3 and len(sleeps) == 2
