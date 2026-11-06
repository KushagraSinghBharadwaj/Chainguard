"""Deterministic token rules (5.2). Pure functions: facts in, evidence out.

GoPlus is a third party, so its flags are never marked verified. Thresholds are initial
guesses, not measured. A missing field produces no evidence: unknown is not False.
"""

import re
from typing import Any

from app.core.addresses import normalize_address

from app.engines.evidence import Evidence
from app.providers.base import ProviderResult
from app.services.contract_data import Section

HIGH_TAX = 0.5
MODERATE_TAX = 0.1


def _ev(id_: str, claim: str, severity: str, data: dict[str, Any], res: ProviderResult[Any]) -> Evidence:
    return Evidence(
        id=id_, kind="provider", claim=claim, severity=severity, confidence=0.6,
        verified=False, data=data, source=res.provider, fetched_at=res.fetched_at,
    )


def goplus_token_evidence(res: ProviderResult[Any]) -> list[Evidence]:
    if res.status != "ok" or res.data is None:
        return []
    t = res.data
    out: list[Evidence] = []
    if t.is_honeypot is True:
        out.append(_ev("provider.goplus.token.honeypot",
                       "GoPlus flags this token as a honeypot: buying may work but selling may not.", "critical", {}, res))
    if t.cannot_buy is True:
        out.append(_ev("provider.goplus.token.cannot_buy", "GoPlus reports this token cannot be bought.", "high", {}, res))
    for name, val in (("sell", t.sell_tax), ("buy", t.buy_tax), ("transfer", t.transfer_tax)):
        if val is None or val < MODERATE_TAX:
            continue
        out.append(_ev(
            f"provider.goplus.token.{name}_tax",
            f"GoPlus reports a {name} tax of {val * 100:.1f}%.",
            "high" if val >= HIGH_TAX else "moderate",
            {"tax": val}, res,
        ))
    if t.is_open_source is False:
        out.append(_ev("provider.goplus.token.not_open_source",
                       "GoPlus reports the contract source is not open, so its code cannot be reviewed.", "moderate", {}, res))
    out.append(_ev(
        "provider.goplus.token.facts",
        "Token facts reported by GoPlus.",
        "info",
        {
            "name": t.name, "symbol": t.symbol, "holder_count": t.holder_count,
            "is_in_dex": t.is_in_dex, "trust_list": t.trust_list, "is_proxy": t.is_proxy,
        },
        res,
    ))
    return out


def proxy_evidence(sec: Section) -> list[Evidence]:
    if sec.status != "ok" or sec.data is None or sec.data.conclusion != "proxy_detected":
        return []
    a = sec.data
    patterns = sorted({f.pattern for f in a.findings})
    source = sec.source or "alchemy,etherscan"
    out = [Evidence(
        id="contract.proxy", kind="rule",
        claim=(
            "This contract is a proxy (" + ", ".join(patterns) + "). If it is upgradable, whoever controls the upgrade "
            "can change its behavior. Admin and upgradability were not checked."
        ),
        severity="info", confidence=1.0, verified=True,
        data={"patterns": patterns, "implementation": a.implementation}, source=source, fetched_at=sec.fetched_at,
    )]
    if a.implementations_disagree:
        out.append(Evidence(
            id="contract.proxy.implementations_disagree", kind="rule",
            claim="Different proxy checks point to different implementation addresses.",
            severity="low", confidence=1.0, verified=True,
            data={"implementations": sorted({f.implementation for f in a.findings if f.implementation})},
            source=source, fetched_at=sec.fetched_at,
        ))
    return out


import json

from app.engines.token_privileges import analyze_privileges


def _parse_abi(source):
    if source is None or not getattr(source, "abi_json", None):
        return None
    try:
        abi = json.loads(source.abi_json)
    except (ValueError, TypeError):
        return None
    return abi if isinstance(abi, list) else None


def privilege_evidence(source_sec: Section, impl_sec: Section) -> list[Evidence]:
    """Facts from the verified ABI. Prefers the implementation ABI for proxies."""
    sec = impl_sec if impl_sec.status == "ok" and impl_sec.data is not None else source_sec
    if sec.status != "ok" or sec.data is None or not sec.data.verified:
        return []
    abi = _parse_abi(sec.data)
    if not abi:
        return []
    out: list[Evidence] = []
    for f in analyze_privileges(abi):
        if f["category"] == "owner_getter" or not f["functions"]:
            continue
        out.append(Evidence(
            id=f"contract.privilege.{f['category']}", kind="rule",
            claim=(f"Verified ABI exposes {f['category']} functions: "
                   + ", ".join(f["functions"]) + ". Presence is a fact, not proof of misuse."),
            severity="info", confidence=1.0, verified=True,
            data={"functions": f["functions"]},
            source=sec.source or "explorer", fetched_at=sec.fetched_at,
        ))
    return out


_OWNER_WORD = re.compile(r"0x[0-9a-fA-F]{64}")


def owner_evidence(res) -> list[Evidence]:
    """owner() read on-chain. A zero address means renounced. Reverts and bad shapes give nothing."""
    if res is None or res.status != "ok" or res.data is None or res.data.reverted:
        return []
    word = res.data.return_data
    if not isinstance(word, str) or not _OWNER_WORD.fullmatch(word):
        return []
    body = word[2:].lower()
    if body[:24] != "0" * 24:
        return []
    if int(body, 16) == 0:
        return [Evidence(
            id="contract.owner.renounced", kind="rule",
            claim="owner() returns the zero address, so ownership looks renounced. Other admin roles may still exist.",
            severity="info", confidence=1.0, verified=True, data={},
            source=res.provider, fetched_at=res.fetched_at,
        )]
    owner = normalize_address("0x" + body[24:])
    return [Evidence(
        id="contract.owner.set", kind="rule",
        claim="owner() returns an active owner address. Whoever controls it can use the owner-only functions.",
        severity="info", confidence=1.0, verified=True, data={"owner": owner},
        source=res.provider, fetched_at=res.fetched_at,
    )]
