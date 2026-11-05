import pytest
from eth_abi import encode
from eth_utils import keccak

from app.providers.alchemy import build_alchemy_client
from app.providers.etherscan import build_etherscan_client
from app.providers.goplus import build_goplus_client
from app.services.calldata import abis_for_contract, decode_calldata
from app.services.contract_data import get_contract_data

pytestmark = pytest.mark.live

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
A = "0x" + "a" * 40


def _call(signature, types, values):
    return "0x" + (keccak(text=signature)[:4] + encode(types, values)).hex()


def _usdc():
    rpc, ex = build_alchemy_client(), build_etherscan_client()
    if rpc is None or ex is None:
        pytest.skip("ALCHEMY_API_KEY or ETHERSCAN_API_KEY is not set in backend/.env")
    return get_contract_data(rpc, ex, build_goplus_client(), 1, USDC)


def test_live_usdc_implementation_abi_decodes_real_functions():
    d = _usdc()
    abis = abis_for_contract(d)
    print("\nabis:", [label for label, _ in abis])
    assert [label for label, _ in abis][0] == "implementation"

    t = decode_calldata(_call("transfer(address,uint256)", ["address", "uint256"], [A, 5]), abis)
    print("transfer:", t.status, t.source, t.abi_label, t.family, t.notes)
    assert t.status == "decoded" and t.source == "verified_abi" and t.abi_label == "implementation"
    assert t.function_name == "transfer"

    m = decode_calldata(_call("configureMinter(address,uint256)", ["address", "uint256"], [A, 5]), abis)
    print("configureMinter:", m.status, m.source, m.abi_label, [a.name for a in m.args])
    assert m.status == "decoded" and m.source == "verified_abi" and m.family is None


def test_live_proxy_abi_alone_cannot_decode_the_token_functions():
    d = _usdc()
    proxy_only = [("contract", d.source.data.abi_json)]
    t = decode_calldata(_call("transfer(address,uint256)", ["address", "uint256"], [A, 5]), proxy_only)
    m = decode_calldata(_call("configureMinter(address,uint256)", ["address", "uint256"], [A, 5]), proxy_only)
    print("\nproxy-only transfer:", t.status, t.source, "| configureMinter:", m.status)
    assert t.status == "decoded" and t.source == "standard_table"
    assert m.status == "unknown_selector"
