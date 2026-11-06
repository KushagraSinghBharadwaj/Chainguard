from datetime import datetime, timezone

from app.engines.evidence import decide_level
from app.engines import token_rules as tr
from app.providers.base import ProviderResult
from app.providers.goplus import GoPlusToken
from app.services.contract_data import ProxyAnalysis, ProxyFinding, Section
from app.services.coverage import CoverageItem

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
COV = [CoverageItem("a", "completed", "s", None, True)]


def _tok(**kw):
    base = dict(address="0x" + "1" * 40, name="T", symbol="T", is_open_source=True, is_proxy=False,
                is_honeypot=False, cannot_buy=False, buy_tax=0.0, sell_tax=0.0, transfer_tax=0.0,
                holder_count=10, trust_list=False, is_in_dex=True, fields_present=frozenset(), raw={})
    base.update(kw)
    return ProviderResult("ok", "goplus", GoPlusToken(**base), None, NOW)


def ids(ev):
    return {e.id for e in ev}


def test_clean_token_only_info():
    ev = tr.goplus_token_evidence(_tok())
    assert ids(ev) == {"provider.goplus.token.facts"}
    assert decide_level(ev, COV) == "LOW"


def test_honeypot_is_high_not_critical_level():
    ev = tr.goplus_token_evidence(_tok(is_honeypot=True))
    assert "provider.goplus.token.honeypot" in ids(ev)
    assert decide_level(ev, COV) == "HIGH"
    assert all(not e.verified for e in ev)


def test_tax_thresholds():
    assert decide_level(tr.goplus_token_evidence(_tok(sell_tax=0.05)), COV) == "LOW"
    assert decide_level(tr.goplus_token_evidence(_tok(sell_tax=0.2)), COV) == "MODERATE"
    ev = tr.goplus_token_evidence(_tok(sell_tax=0.9))
    assert next(e for e in ev if e.id.endswith("sell_tax")).severity == "high"


def test_missing_fields_make_no_evidence():
    ev = tr.goplus_token_evidence(_tok(is_honeypot=None, cannot_buy=None, sell_tax=None, is_open_source=None))
    assert ids(ev) == {"provider.goplus.token.facts"}


def test_not_open_source_moderate():
    assert decide_level(tr.goplus_token_evidence(_tok(is_open_source=False)), COV) == "MODERATE"


def test_trust_list_never_lowers():
    ev = tr.goplus_token_evidence(_tok(is_honeypot=True, trust_list=True))
    assert decide_level(ev, COV) == "HIGH"


def test_failed_provider_gives_nothing():
    assert tr.goplus_token_evidence(ProviderResult("unavailable", "goplus", None, "x")) == []


def _proxy(conclusion, impls=("0x" + "a" * 40,)):
    findings = tuple(ProxyFinding("eip1967_implementation", i, None, "storage_slot", None) for i in impls)
    a = ProxyAnalysis(conclusion, findings, (), impls[0] if impls else None, len(set(impls)) > 1)
    return Section("proxy_detection", "ok", a, None, "alchemy,etherscan", NOW)


def test_proxy_is_info_only():
    ev = tr.proxy_evidence(_proxy("proxy_detected"))
    assert ids(ev) == {"contract.proxy"} and decide_level(ev, COV) == "LOW"


def test_proxy_disagreement_is_moderate():
    ev = tr.proxy_evidence(_proxy("proxy_detected", ("0x" + "a" * 40, "0x" + "b" * 40)))
    assert decide_level(ev, COV) == "MODERATE"


def test_no_pattern_or_unknown_gives_nothing():
    assert tr.proxy_evidence(_proxy("no_known_pattern_found", ())) == []
    assert tr.proxy_evidence(_proxy("unknown", ())) == []


import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.engines.token_rules import privilege_evidence
from app.services.contract_data import Section


def _sec(abi, verified=True):
    d = SimpleNamespace(verified=verified, abi_json=json.dumps(abi))
    return Section("verified_source", "ok", d, None, "etherscan", datetime.now(timezone.utc))


_SKIP = Section("implementation_source", "skipped", None, None, None, None)


def test_privilege_evidence_from_abi():
    abi = [{"type": "function", "name": "pause"}, {"type": "function", "name": "mint"}]
    ids = {e.id for e in privilege_evidence(_sec(abi), _SKIP)}
    assert ids == {"contract.privilege.pause", "contract.privilege.mint"}


def test_unverified_gives_nothing():
    assert privilege_evidence(_sec([], verified=False), _SKIP) == []


from app.engines.token_rules import owner_evidence
from app.providers.base import ProviderResult


def _owner_res(word, reverted=False):
    out = SimpleNamespace(reverted=reverted, return_data=word)
    return ProviderResult("ok", "alchemy", out, None, datetime.now(timezone.utc))


def test_owner_renounced():
    ev = owner_evidence(_owner_res("0x" + "0" * 64))
    assert [e.id for e in ev] == ["contract.owner.renounced"]


def test_owner_set():
    ev = owner_evidence(_owner_res("0x" + "0" * 24 + "ab" * 20))
    assert [e.id for e in ev] == ["contract.owner.set"]


def test_owner_revert_or_none():
    assert owner_evidence(_owner_res("0x", reverted=True)) == []
    assert owner_evidence(None) == []
