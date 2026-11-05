import pytest

from app.providers.alchemy import build_alchemy_client

pytestmark = pytest.mark.live

WALLET = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
USDC_PROXY = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


def _client():
    client = build_alchemy_client()
    if client is None:
        pytest.skip("ALCHEMY_API_KEY is not set in backend/.env")
    return client


def test_live_contract_has_code():
    r = _client().get_code(1, WETH)
    print("\nweth code:", r.status, r.detail, len(r.data or ""))
    assert r.status == "ok" and len(r.data) > 100


def test_live_wallet_has_no_code():
    r = _client().get_code(1, WALLET)
    print("\nwallet code:", r.status, r.detail, r.data)
    assert r.status == "ok" and r.data == "0x"


def test_live_symbol_call():
    r = _client().eth_call(1, WETH, "0x95d89b41")
    print("\nsymbol():", r.status, r.detail, r.data and r.data.reverted)
    assert r.status == "ok" and r.data.reverted is False and len(r.data.return_data) > 2


def test_live_revert_is_reported():
    # transfer(0x2222..., 1) from an address that holds no WETH must revert.
    data = "0xa9059cbb" + "0" * 24 + "2" * 40 + "%064x" % 1
    r = _client().eth_call(1, WETH, data, from_address="0x" + "1" * 40)
    print("\nrevert call:", r.status, r.detail, r.data)
    assert r.status == "ok" and r.data.reverted is True


def test_live_eip1967_implementation_slot():
    r = _client().get_storage_at(1, USDC_PROXY, EIP1967_IMPL_SLOT)
    print("\nusdc impl slot:", r.status, r.detail, r.data)
    assert r.status == "ok" and len(r.data) == 66 and int(r.data, 16) != 0
