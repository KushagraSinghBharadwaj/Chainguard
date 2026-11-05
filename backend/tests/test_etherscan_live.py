import pytest

from app.providers.etherscan import build_etherscan_client

pytestmark = pytest.mark.live

# Public, well-known addresses. Real Etherscan calls with your real key.
KNOWN_WALLET = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
VERIFIED_CONTRACT = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def _client():
    client = build_etherscan_client()
    if client is None:
        pytest.skip("ETHERSCAN_API_KEY is not set in backend/.env")
    return client


def test_live_transactions():
    r = _client().get_transactions(1, KNOWN_WALLET, page_size=5)
    print("\ntransactions:", r.status, r.detail, len(r.data or []))
    assert r.status == "ok" and len(r.data) == 5
    assert all(t.from_address.startswith("0x") for t in r.data)


def test_live_token_transfers():
    r = _client().get_token_transfers(1, KNOWN_WALLET, page_size=5)
    print("\ntoken transfers:", r.status, r.detail, len(r.data or []))
    assert r.status == "ok" and len(r.data) == 5


def test_live_verified_contract():
    r = _client().get_contract_source(1, VERIFIED_CONTRACT)
    print("\nverified contract:", r.status, r.detail, r.data and r.data.contract_name)
    assert r.status == "ok" and r.data.verified and r.data.abi_json


def test_live_wallet_address_is_not_reported_as_verified_contract():
    r = _client().get_contract_source(1, KNOWN_WALLET)
    print("\nunverified shape:", r.status, r.detail, r.data)
    assert r.status in ("ok", "not_found", "unavailable")
    if r.status == "ok":
        assert r.data.verified is False
