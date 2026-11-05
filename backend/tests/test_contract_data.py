from types import SimpleNamespace

import pytest

from app.providers.base import CallOutcome, ContractSource, ProviderResult
from app.services.contract_data import (
    SLOT_EIP1967_BEACON,
    SLOT_EIP1967_IMPLEMENTATION,
    SLOT_ZOS_IMPLEMENTATION,
    get_contract_data,
)

ADDR = "0x" + "a" * 40
IMPL = "0x" + "1" * 40
BEACON = "0x" + "2" * 40
OTHER = "0x" + "3" * 40
ZERO = "0x" + "0" * 64
PLAIN_CODE = "0x6080604052"
SELECTOR = "0x5c60da1b"


def word(address):
    return "0x" + "0" * 24 + address[2:]


def verified(**over):
    base = dict(
        verified=True, contract_name="X", compiler_version="v0.8.0",
        abi_json="[]", is_proxy=False, implementation=None,
    )
    base.update(over)
    return ContractSource(**base)


class FakeRpc:
    """FIXTURE (synthetic): scripted RPC answers. Test-only, never imported by product code.
    Real behavior is covered by the live tests (pytest --live)."""

    def __init__(self, code="0x", code_status="ok", slots=None, default_slot=ZERO, calls=None):
        self.code, self.code_status = code, code_status
        self.slots, self.default_slot = slots or {}, default_slot
        self.calls = calls or {}
        self.log = []

    def get_code(self, chain_id, address):
        self.log.append(("code", address))
        if self.code_status != "ok":
            return ProviderResult(self.code_status, "fake", None, "injected")
        return ProviderResult("ok", "fake", self.code)

    def get_storage_at(self, chain_id, address, slot):
        self.log.append(("slot", slot))
        value = self.slots.get(slot, self.default_slot)
        if isinstance(value, ProviderResult):
            return value
        return ProviderResult("ok", "fake", value)

    def eth_call(self, chain_id, to, data, *, from_address=None):
        self.log.append(("call", to, data))
        return self.calls.get(to, ProviderResult("unavailable", "fake", None, "no_fake"))


class FakeExplorer:
    def __init__(self, by_address=None, default=None):
        self.by_address = by_address or {}
        self.default = default or ProviderResult("ok", "fake", verified())
        self.log = []

    def get_contract_source(self, chain_id, address):
        self.log.append(address)
        return self.by_address.get(address, self.default)


class FakeToken:
    def __init__(self, result=None):
        self.result = result or ProviderResult("ok", "fake", SimpleNamespace(symbol="TKN"))
        self.log = []

    def token_security(self, chain_id, address):
        self.log.append(address)
        return self.result


def run(rpc, explorer=None, token=None, address=ADDR):
    return get_contract_data(rpc, explorer or FakeExplorer(), token or FakeToken(), 1, address)


def test_slot_constants_match_the_published_values():
    assert SLOT_EIP1967_IMPLEMENTATION == "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
    assert SLOT_EIP1967_BEACON == "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
    assert SLOT_ZOS_IMPLEMENTATION == "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3"


def test_no_code_skips_everything_and_makes_no_other_calls():
    rpc, exp, tok = FakeRpc(code="0x"), FakeExplorer(), FakeToken()
    d = run(rpc, exp, tok)
    assert d.bytecode.status == "ok" and d.bytecode.data.kind == "no_code"
    assert d.bytecode.data.size_bytes == 0 and d.bytecode.data.code_hash is None
    for s in (d.source, d.proxy, d.implementation_source, d.token):
        assert s.status == "skipped" and s.detail == "no_code"
    assert exp.log == [] and tok.log == [] and rpc.log == [("code", ADDR)]


def test_eip7702_delegation_is_reported_and_contract_checks_are_skipped():
    target = "0x" + "ab" * 20
    rpc, exp, tok = FakeRpc(code="0xef0100" + target[2:]), FakeExplorer(), FakeToken()
    d = run(rpc, exp, tok)
    assert d.bytecode.data.kind == "eip7702_delegation"
    assert d.bytecode.data.delegation_target == target
    for s in (d.source, d.proxy, d.implementation_source, d.token):
        assert s.status == "skipped" and s.detail == "eip7702_delegation"
    assert exp.log == [] and tok.log == [] and rpc.log == [("code", ADDR)]


def test_plain_contract_has_no_known_proxy_pattern():
    d = run(FakeRpc(code=PLAIN_CODE))
    assert d.bytecode.data.kind == "contract" and d.bytecode.data.size_bytes == 5
    assert d.bytecode.data.code_hash.startswith("0x") and len(d.bytecode.data.code_hash) == 66
    assert d.source.status == "ok" and d.source.data.verified
    p = d.proxy.data
    assert d.proxy.status == "ok" and p.conclusion == "no_known_pattern_found"
    assert p.findings == () and len(p.checks) == 5
    assert all(c.status == "completed" and not c.found for c in p.checks)
    assert d.implementation_source.status == "skipped"
    assert d.implementation_source.detail == "no_implementation_found"
    assert d.token.status == "ok" and d.token.data.symbol == "TKN"


def test_eip1967_proxy_fetches_the_implementation_source():
    rpc = FakeRpc(code=PLAIN_CODE, slots={SLOT_EIP1967_IMPLEMENTATION: word(IMPL)})
    exp = FakeExplorer(by_address={IMPL: ProviderResult("ok", "fake", verified(contract_name="Impl"))})
    d = run(rpc, exp)
    p = d.proxy.data
    assert p.conclusion == "proxy_detected" and p.implementation == IMPL
    assert [f.pattern for f in p.findings] == ["eip1967_implementation"]
    assert d.implementation_source.status == "ok" and d.implementation_source.data.contract_name == "Impl"
    assert exp.log == [ADDR, IMPL]


def test_legacy_zos_slot_is_detected_when_eip1967_slot_is_empty():
    d = run(FakeRpc(code=PLAIN_CODE, slots={SLOT_ZOS_IMPLEMENTATION: word(IMPL)}))
    p = d.proxy.data
    assert p.conclusion == "proxy_detected" and p.implementation == IMPL
    assert [f.pattern for f in p.findings] == ["zos_legacy"]
    eip1967 = next(c for c in p.checks if c.pattern == "eip1967_implementation")
    assert eip1967.status == "completed" and eip1967.found is False


def test_eip1167_minimal_proxy_is_read_from_bytecode():
    code = "0x363d3d373d3d3d363d73" + IMPL[2:] + "5af43d82803e903d91602b57fd5bf3"
    d = run(FakeRpc(code=code))
    assert d.bytecode.data.clone_target == IMPL
    f = d.proxy.data.findings[0]
    assert f.pattern == "eip1167_minimal" and f.implementation == IMPL and f.evidence_source == "bytecode"


def test_beacon_is_resolved_through_the_beacon_contract():
    rpc = FakeRpc(
        code=PLAIN_CODE,
        slots={SLOT_EIP1967_BEACON: word(BEACON)},
        calls={BEACON: ProviderResult("ok", "fake", CallOutcome(False, word(IMPL)))},
    )
    d = run(rpc)
    f = d.proxy.data.findings[0]
    assert f.pattern == "eip1967_beacon" and f.implementation == IMPL and f.beacon == BEACON
    assert ("call", BEACON, SELECTOR) in rpc.log


def test_beacon_that_reverts_is_a_finding_without_an_implementation():
    rpc = FakeRpc(
        code=PLAIN_CODE,
        slots={SLOT_EIP1967_BEACON: word(BEACON)},
        calls={BEACON: ProviderResult("ok", "fake", CallOutcome(True, None))},
    )
    d = run(rpc)
    f = d.proxy.data.findings[0]
    assert f.implementation is None and f.detail == "beacon_call_reverted"
    assert d.proxy.data.conclusion == "proxy_detected" and d.proxy.data.implementation is None
    assert d.implementation_source.status == "skipped"


def test_a_failed_slot_read_means_unknown_not_clean():
    failed = ProviderResult("unavailable", "fake", None, "injected")
    d = run(FakeRpc(code=PLAIN_CODE, slots={SLOT_EIP1967_IMPLEMENTATION: failed}))
    p = d.proxy.data
    assert p.conclusion == "unknown" and d.proxy.status == "ok"
    chk = next(c for c in p.checks if c.pattern == "eip1967_implementation")
    assert chk.status == "unavailable" and chk.detail == "injected"


def test_every_check_failing_makes_the_section_unavailable():
    failed = ProviderResult("unavailable", "fake", None, "injected")
    rpc = FakeRpc(code_status="unavailable", default_slot=failed)
    exp = FakeExplorer(default=ProviderResult("unavailable", "fake", None, "injected"))
    d = run(rpc, exp)
    assert d.bytecode.status == "unavailable" and d.source.status == "unavailable"
    assert d.proxy.status == "unavailable" and d.proxy.detail == "all_checks_failed"
    assert d.proxy.data.conclusion == "unknown"


def test_unavailable_bytecode_does_not_stop_the_other_checks():
    d = run(FakeRpc(code_status="rate_limited"))
    assert d.bytecode.status == "rate_limited"
    assert d.source.status == "ok" and d.token.status == "ok"
    clone = next(c for c in d.proxy.data.checks if c.pattern == "eip1167_minimal")
    assert clone.status == "skipped" and clone.detail == "bytecode_unavailable"
    assert d.proxy.data.conclusion == "unknown"


def test_explorer_proxy_flag_is_a_finding_even_when_slots_are_empty():
    exp = FakeExplorer(default=ProviderResult("ok", "fake", verified(is_proxy=True, implementation=IMPL)))
    d = run(FakeRpc(code=PLAIN_CODE), exp)
    p = d.proxy.data
    assert p.conclusion == "proxy_detected" and p.implementation == IMPL
    assert [f.pattern for f in p.findings] == ["etherscan_reported"]
    assert exp.log == [ADDR, IMPL]


def test_sources_that_disagree_are_both_reported():
    rpc = FakeRpc(code=PLAIN_CODE, slots={SLOT_EIP1967_IMPLEMENTATION: word(IMPL)})
    exp = FakeExplorer(
        by_address={ADDR: ProviderResult("ok", "fake", verified(is_proxy=True, implementation=OTHER))}
    )
    d = run(rpc, exp)
    p = d.proxy.data
    assert [f.pattern for f in p.findings] == ["eip1967_implementation", "etherscan_reported"]
    assert p.implementation == IMPL and p.implementations_disagree is True


@pytest.mark.parametrize("value,detail", [("0x" + "ff" * 32, "not_an_address"), ("0x1234", "unexpected_shape")])
def test_garbage_slot_values_are_unavailable(value, detail):
    d = run(FakeRpc(code=PLAIN_CODE, slots={SLOT_ZOS_IMPLEMENTATION: value}))
    chk = next(c for c in d.proxy.data.checks if c.pattern == "zos_legacy")
    assert chk.status == "unavailable" and chk.detail == detail and chk.found is False
    assert d.proxy.data.conclusion == "unknown"


def test_explorer_failure_blocks_a_clean_conclusion():
    exp = FakeExplorer(default=ProviderResult("rate_limited", "fake", None, "injected"))
    d = run(FakeRpc(code=PLAIN_CODE), exp)
    assert d.source.status == "rate_limited"
    chk = next(c for c in d.proxy.data.checks if c.pattern == "etherscan_reported")
    assert chk.status == "rate_limited"
    assert d.proxy.data.conclusion == "unknown"


def test_token_not_found_passes_through_unchanged():
    tok = FakeToken(ProviderResult("not_found", "fake", None, "no_data_for_token"))
    d = run(FakeRpc(code=PLAIN_CODE), token=tok)
    assert d.token.status == "not_found" and d.token.data is None and d.token.detail == "no_data_for_token"


@pytest.mark.parametrize("code", ["0xzz", "0x123", "6080"])
def test_malformed_bytecode_is_unavailable(code):
    d = run(FakeRpc(code=code))
    assert d.bytecode.status == "unavailable" and d.bytecode.detail == "unexpected_shape"


def test_invalid_address_makes_no_calls():
    rpc, exp, tok = FakeRpc(), FakeExplorer(), FakeToken()
    with pytest.raises(ValueError):
        get_contract_data(rpc, exp, tok, 1, "0x123")
    assert rpc.log == [] and exp.log == [] and tok.log == []
