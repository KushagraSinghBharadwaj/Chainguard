import json
from types import SimpleNamespace

import pytest
from eth_abi import encode
from eth_utils import keccak

from app.services.calldata import STANDARD_BY_SELECTOR, abis_for_contract, decode_calldata

# FIXTURES: calldata is built locally with eth-abi (synthetic). Test-only, never imported by
# product code. Real ABIs are exercised by the live tests (pytest --live).

A = "0x" + "a" * 40
B = "0x" + "b" * 40
MAX_UINT = 2**256 - 1


def raw_call(signature, types, values):
    return keccak(text=signature)[:4] + encode(types, values)


def call(signature, types, values):
    return "0x" + raw_call(signature, types, values).hex()


def inp(type_, name, components=None):
    d = {"name": name, "type": type_}
    if components:
        d["components"] = components
    return d


def fn(name, *inputs):
    return {"type": "function", "name": name, "inputs": list(inputs), "outputs": [], "stateMutability": "nonpayable"}


def abi(*functions):
    return json.dumps(list(functions))


def test_known_standard_selectors():
    expected = {
        "0xa9059cbb": "transfer(address,uint256)",
        "0x095ea7b3": "approve(address,uint256)",
        "0x23b872dd": "transferFrom(address,address,uint256)",
        "0xa22cb465": "setApprovalForAll(address,bool)",
        "0x42842e0e": "safeTransferFrom(address,address,uint256)",
        "0xb88d4fde": "safeTransferFrom(address,address,uint256,bytes)",
        "0xf242432a": "safeTransferFrom(address,address,uint256,uint256,bytes)",
        "0x2eb2c2d6": "safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)",
        "0xd505accf": "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
        "0xd0e30db0": "deposit()",
        "0x2e1a7d4d": "withdraw(uint256)",
        "0xac9650d8": "multicall(bytes[])",
    }
    for selector, signature in expected.items():
        assert STANDARD_BY_SELECTOR[selector].signature == signature


def test_transfer_decodes_from_the_standard_table():
    r = decode_calldata(call("transfer(address,uint256)", ["address", "uint256"], [A, 1000]))
    assert r.status == "decoded" and r.source == "standard_table" and r.family == "erc20"
    assert r.signature == "transfer(address,uint256)" and r.function_name == "transfer"
    assert [(a.type, a.value) for a in r.args] == [("address", A), ("uint256", 1000)]
    assert r.notes == () and r.abi_label is None


def test_approve_is_marked_as_shared_between_erc20_and_erc721():
    r = decode_calldata(call("approve(address,uint256)", ["address", "uint256"], [A, MAX_UINT]))
    assert r.status == "decoded" and r.family == "erc20_or_erc721"
    assert r.args[1].value == MAX_UINT
    assert "selector_shared_by_erc20_and_erc721" in r.notes


def test_transfer_from_is_marked_as_shared():
    r = decode_calldata(call("transferFrom(address,address,uint256)", ["address", "address", "uint256"], [A, B, 7]))
    assert r.status == "decoded" and "selector_shared_by_erc20_and_erc721" in r.notes


def test_set_approval_for_all_decodes_a_bool():
    r = decode_calldata(call("setApprovalForAll(address,bool)", ["address", "bool"], [A, True]))
    assert r.status == "decoded" and r.args[1].value is True and r.family == "erc721_or_erc1155"


def test_empty_calldata_is_no_calldata():
    assert decode_calldata("0x").status == "no_calldata"


@pytest.mark.parametrize("data", ["", "0x12", "0xzz", "0x123", "abcd", 5, None])
def test_malformed_input(data):
    r = decode_calldata(data)
    assert r.status == "malformed" and r.detail in ("invalid_hex", "shorter_than_selector")


def test_oversized_calldata_is_malformed():
    assert decode_calldata("0x" + "00" * 100_002).status == "malformed"


def test_unknown_selector_is_reported_unknown_not_guessed():
    r = decode_calldata("0xdeadbeef" + "00" * 32)
    assert r.status == "unknown_selector" and r.selector == "0xdeadbeef"
    assert r.signature is None and r.args == () and r.source is None
    assert r.detail == "selector_not_in_known_abis_or_standard_table"


def test_truncated_arguments_are_a_failed_decode():
    r = decode_calldata("0xa9059cbb" + "00" * 10)
    assert r.status == "decode_failed" and r.function_name == "transfer" and r.detail
    assert r.args == ()


def test_verified_abi_decodes_with_names_and_label():
    a = abi(fn("claim", inp("address", "to"), inp("uint256", "amount")))
    r = decode_calldata(call("claim(address,uint256)", ["address", "uint256"], [A, 5]), [("contract", a)])
    assert r.status == "decoded" and r.source == "verified_abi" and r.abi_label == "contract"
    assert [x.name for x in r.args] == ["to", "amount"] and r.family is None


def test_abi_function_with_the_standard_signature_gets_the_standard_family():
    a = abi(fn("transfer", inp("address", "to"), inp("uint256", "value")))
    r = decode_calldata(call("transfer(address,uint256)", ["address", "uint256"], [A, 1]), [("implementation", a)])
    assert r.source == "verified_abi" and r.family == "erc20" and r.abi_label == "implementation"


def test_a_contract_declared_name_does_not_earn_a_standard_family():
    a = abi(fn("transfer", inp("uint256", "x")))
    r = decode_calldata(call("transfer(uint256)", ["uint256"], [9]), [("contract", a)])
    assert r.status == "decoded" and r.source == "verified_abi"
    assert r.signature == "transfer(uint256)" and r.family is None


def test_tuple_arrays_are_decoded_and_normalized():
    a = abi(fn("exec", inp("tuple[]", "calls", [inp("address", "target"), inp("uint256", "value")])))
    data = call("exec((address,uint256)[])", ["(address,uint256)[]"], [[(A, 5), (B, 6)]])
    r = decode_calldata(data, [("contract", a)])
    assert r.status == "decoded" and r.args[0].type == "(address,uint256)[]"
    assert r.args[0].value == [[A, 5], [B, 6]]


def test_string_and_bytes_arguments():
    a = abi(fn("note", inp("string", "text"), inp("bytes", "blob")))
    r = decode_calldata(call("note(string,bytes)", ["string", "bytes"], ["hello", b"\x01\x02"]), [("contract", a)])
    assert [x.value for x in r.args] == ["hello", "0x0102"]


def test_first_abi_in_the_list_wins():
    one = abi(fn("claim", inp("address", "first"), inp("uint256", "n")))
    two = abi(fn("claim", inp("address", "second"), inp("uint256", "n")))
    data = call("claim(address,uint256)", ["address", "uint256"], [A, 1])
    r = decode_calldata(data, [("implementation", one), ("contract", two)])
    assert r.abi_label == "implementation" and r.args[0].name == "first"


def test_unparseable_abi_is_noted_and_the_standard_table_still_works():
    bad = ("contract", "Contract source code not verified")
    r = decode_calldata(call("transfer(address,uint256)", ["address", "uint256"], [A, 1]), [bad])
    assert r.status == "decoded" and r.source == "standard_table"
    assert "abi_unparseable:contract" in r.notes
    u = decode_calldata("0xdeadbeef", [bad])
    assert u.status == "unknown_selector" and "abi_unparseable:contract" in u.notes


def test_no_argument_function_with_extra_bytes_is_noted():
    assert decode_calldata("0xd0e30db0").notes == ()
    r = decode_calldata("0xd0e30db0" + "00" * 4)
    assert r.status == "decoded" and r.signature == "deposit()" and "trailing_bytes_ignored" in r.notes


def test_multicall_decodes_the_inner_calls():
    inner_a = raw_call("transfer(address,uint256)", ["address", "uint256"], [A, 1])
    inner_b = raw_call("approve(address,uint256)", ["address", "uint256"], [B, MAX_UINT])
    r = decode_calldata(call("multicall(bytes[])", ["bytes[]"], [[inner_a, inner_b]]))
    assert r.status == "decoded" and r.family == "multicall" and len(r.inner_calls) == 2
    assert r.inner_calls[0].signature == "transfer(address,uint256)"
    assert r.inner_calls[1].signature == "approve(address,uint256)"
    assert "selector_shared_by_erc20_and_erc721" in r.inner_calls[1].notes
    assert r.args[0].value[0] == "0x" + inner_a.hex()


def test_multicall_nesting_is_capped():
    data = raw_call("transfer(address,uint256)", ["address", "uint256"], [A, 1])
    for _ in range(4):
        data = raw_call("multicall(bytes[])", ["bytes[]"], [[data]])
    node = decode_calldata("0x" + data.hex())
    depth = 0
    while node.inner_calls:
        node = node.inner_calls[0]
        depth += 1
    assert depth == 3 and node.signature == "multicall(bytes[])"
    assert "nested_depth_limit" in node.notes


def test_multicall_inner_call_count_is_capped():
    inner = raw_call("transfer(address,uint256)", ["address", "uint256"], [A, 1])
    r = decode_calldata(call("multicall(bytes[])", ["bytes[]"], [[inner] * 51]))
    assert len(r.inner_calls) == 50 and "inner_calls_truncated" in r.notes


def test_abis_for_contract_orders_implementation_first_and_skips_unusable():
    def src(verified, abi_json):
        return SimpleNamespace(status="ok", data=SimpleNamespace(verified=verified, abi_json=abi_json))

    both = SimpleNamespace(implementation_source=src(True, "[1]"), source=src(True, "[2]"))
    assert abis_for_contract(both) == [("implementation", "[1]"), ("contract", "[2]")]
    skipped = SimpleNamespace(
        implementation_source=SimpleNamespace(status="skipped", data=None), source=src(False, None)
    )
    assert abis_for_contract(skipped) == []
