import asyncio

import httpx

from app.core.config import Settings
from app.services.ollama_client import generate_explanation

SUMMARY = (
    "MODERATE risk. Verified ABI exposes blacklist functions: addBlackList, removeBlackList. "
    "Presence is a fact, not proof of misuse. owner() returns an active owner address."
)
REPORT = {"risk_level": "MODERATE", "summary": SUMMARY}
GOOD = (
    "Risk level: MODERATE. The contract code lists blacklist functions, which is a fact and "
    "not proof of misuse. It also has an active owner address."
)


def run(report, *, enabled=True, handler=None):
    calls = []

    def default(request):
        calls.append(request)
        return httpx.Response(200, json={"message": {"content": GOOD}})

    def wrapped(request):
        calls.append(request)
        return handler(request)

    transport = httpx.MockTransport(wrapped if handler else default)
    cfg = Settings(llm_enabled=enabled)
    result = asyncio.run(generate_explanation(report, settings=cfg, transport=transport))
    return result, calls


def test_disabled_makes_no_call():
    result, calls = run(REPORT, enabled=False)
    assert result is None and calls == []


def test_low_level_makes_no_call():
    result, calls = run({"risk_level": "LOW", "summary": "No findings."})
    assert result is None and calls == []


def test_good_output_is_returned():
    result, calls = run(REPORT)
    assert len(calls) == 1
    assert result["text"] == GOOD
    assert result["validated"] is True and result["source"] == "local-llm"


def test_wrong_level_is_discarded():
    bad = {"message": {"content": "Risk level: HIGH. The contract lists blacklist functions."}}
    result, _ = run(REPORT, handler=lambda r: httpx.Response(200, json=bad))
    assert result is None


def test_server_error_fails_open():
    result, _ = run(REPORT, handler=lambda r: httpx.Response(500, json={"error": "boom"}))
    assert result is None


def test_connection_error_fails_open():
    def boom(request):
        raise httpx.ConnectError("ollama is not running")

    result, _ = run(REPORT, handler=boom)
    assert result is None