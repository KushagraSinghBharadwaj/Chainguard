"""Deterministic wallet rules. Pure functions: facts in, evidence objects out.

Every finding says where it came from. List matches are verified facts about list
membership. GoPlus flags are a third party's assessment, so they are not marked verified.
"""

import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from app.engines.evidence import Evidence
from app.providers.base import ProviderResult
from app.services.contract_data import ContractData
from app.services.intel_lookup import IntelHit
from app.services.wallet_data import WalletHistory

NOT_RISK_FLAGS = frozenset({"contract_address"})
SAMPLE_SIZE = 5


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unknown"


def is_ofac(source: str) -> bool:
    return "ofac" in source.lower()


def subject_intel_evidence(hits: Iterable[IntelHit]) -> list[Evidence]:
    out = []
    for h in hits:
        label = f" ({h.label})" if h.label else ""
        if is_ofac(h.source):
            claim, severity = f"This address is on the {h.source} sanctions list{label}.", "critical"
        else:
            claim, severity = f"This address is on the {h.source} list as {h.category}{label}.", "high"
        out.append(
            Evidence(
                id=f"intel.{slug(h.source)}.{slug(h.category)}.subject",
                kind="intel",
                claim=claim,
                severity=severity,
                confidence=1.0,
                verified=True,
                data={"source": h.source, "category": h.category, "label": h.label, "list_version": h.list_version},
                source=h.source,
                fetched_at=h.fetched_at,
            )
        )
    return out


def counterparty_evidence(counterparty_hits: dict[str, tuple[IntelHit, ...]]) -> list[Evidence]:
    by_source: dict[str, dict[str, IntelHit]] = {}
    for address, hits in counterparty_hits.items():
        for h in hits:
            by_source.setdefault(h.source, {})[address] = h
    out = []
    for source, found in sorted(by_source.items()):
        severity = "high" if is_ofac(source) else "moderate"
        newest = max((h.fetched_at for h in found.values() if h.fetched_at), default=None)
        out.append(
            Evidence(
                id=f"intel.{slug(source)}.counterparties",
                kind="intel",
                claim=f"{len(found)} address(es) this wallet exchanged funds or tokens with, in the fetched history, appear on the {source} list.",
                severity=severity,
                confidence=1.0,
                verified=True,
                data={"count": len(found), "sample": sorted(found)[:SAMPLE_SIZE]},
                source=source,
                fetched_at=newest,
            )
        )
    return out


def goplus_evidence(res: ProviderResult[Any]) -> list[Evidence]:
    if res.status != "ok" or res.data is None:
        return []
    out = []
    flags = getattr(res.data, "flags", None) or {}
    raised = sorted(n for n, v in flags.items() if v is True and n not in NOT_RISK_FLAGS)
    if raised:
        out.append(
            Evidence(
                id="provider.goplus.flags",
                kind="provider",
                claim="GoPlus flags this address: " + ", ".join(raised) + ".",
                severity="high",
                confidence=0.6,
                verified=False,
                data={"flags": raised},
                source=res.provider,
                fetched_at=res.fetched_at,
            )
        )
    created = getattr(res.data, "malicious_contracts_created", None)
    if isinstance(created, int) and created > 0:
        out.append(
            Evidence(
                id="provider.goplus.malicious_contracts",
                kind="provider",
                claim=f"GoPlus reports this address created {created} contract(s) it considers malicious.",
                severity="high",
                confidence=0.6,
                verified=False,
                data={"count": created},
                source=res.provider,
                fetched_at=res.fetched_at,
            )
        )
    return out


def code_evidence(contract: ContractData) -> list[Evidence]:
    sec = contract.bytecode
    if sec.status != "ok" or sec.data is None:
        return []
    info = sec.data
    source = sec.source or "alchemy"
    if info.kind == "eip7702_delegation":
        return [
            Evidence(
                id="code.eip7702",
                kind="provider",
                claim=f"This account has EIP-7702 delegated code pointing to {info.delegation_target}.",
                severity="low",
                confidence=1.0,
                verified=True,
                data={"delegation_target": info.delegation_target},
                source=source,
                fetched_at=sec.fetched_at,
            )
        ]
    if info.kind == "contract":
        return [
            Evidence(
                id="code.is_contract",
                kind="provider",
                claim="This address is a smart contract, not a regular wallet, so wallet checks apply only partly. Use token and contract analysis.",
                severity="info",
                confidence=1.0,
                verified=True,
                data={"size_bytes": info.size_bytes},
                source=source,
                fetched_at=sec.fetched_at,
            )
        ]
    return []


def history_evidence(history: WalletHistory, now: datetime) -> list[Evidence]:
    out = []
    tx = history.transactions
    out.append(
        Evidence(
            id="wallet.history_size",
            kind="provider",
            claim=f"{len(tx.items)} transaction(s) were fetched; the history is {tx.status}.",
            severity="info",
            confidence=1.0,
            verified=True,
            data={"fetched": len(tx.items), "status": tx.status, "stop_reason": tx.stop_reason},
            source=tx.source,
            fetched_at=tx.fetched_at,
        )
    )
    first = history.first_transaction
    if first.status == "complete" and first.items:
        ts = first.items[0].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days = max(0, (now - ts).days)
        out.append(
            Evidence(
                id="wallet.age",
                kind="provider",
                claim=f"The first transaction on record was on {ts.date().isoformat()} ({days} days ago).",
                severity="info",
                confidence=1.0,
                verified=True,
                data={"first_seen": ts.isoformat(), "age_days": days},
                source=first.source,
                fetched_at=first.fetched_at,
            )
        )
    return out
