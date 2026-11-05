import pytest

from app.providers.goplus import GoPlusClient

pytestmark = pytest.mark.live

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"


def test_live_token_security_usdc():
    r = GoPlusClient().token_security(1, USDC)
    print("\ntoken:", r.status, r.detail, r.data and (r.data.symbol, r.data.is_proxy, r.data.is_honeypot))
    assert r.status == "ok" and r.data.symbol == "USDC"


def test_live_unknown_token_is_not_found():
    r = GoPlusClient().token_security(1, "0x" + "12" * 20)
    print("\nunknown token:", r.status, r.detail)
    assert r.status == "not_found"


def test_live_address_security_returns_flags():
    r = GoPlusClient().address_security(1, "0x0330070fd38ec3bb94f58fa55d40368271e9e54a")
    print("\naddress:", r.status, r.detail, r.data and (r.data.positive_flags(), r.data.data_sources))
    assert r.status == "ok" and "sanctioned" in r.data.flags
