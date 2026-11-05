import pytest

from app.providers.alchemy import build_alchemy_client
from app.providers.etherscan import build_etherscan_client
from app.providers.goplus import build_goplus_client
from app.services.contract_data import get_contract_data

pytestmark = pytest.mark.live

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WALLET = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"


def _data(address):
    rpc, ex = build_alchemy_client(), build_etherscan_client()
    if rpc is None or ex is None:
        pytest.skip("ALCHEMY_API_KEY or ETHERSCAN_API_KEY is not set in backend/.env")
    return get_contract_data(rpc, ex, build_goplus_client(), 1, address)


def test_live_usdc_is_a_detected_proxy_with_an_implementation():
    d = _data(USDC)
    assert d.bytecode.status == "ok" and d.bytecode.data.kind == "contract"
    assert d.source.status == "ok" and d.source.data.verified
    assert d.proxy.data.conclusion == "proxy_detected" and d.proxy.data.implementation
    assert d.implementation_source.status == "ok"
    assert d.token.status == "ok"


def test_live_weth_has_no_known_proxy_pattern():
    d = _data(WETH)
    assert d.proxy.data.conclusion == "no_known_pattern_found"
    assert all(c.status == "completed" for c in d.proxy.data.checks)


def test_live_account_skips_contract_checks():
    d = _data(WALLET)
    assert d.bytecode.status == "ok" and d.bytecode.data.kind in ("no_code", "eip7702_delegation")
    assert d.source.status == "skipped" and d.token.status == "skipped"
