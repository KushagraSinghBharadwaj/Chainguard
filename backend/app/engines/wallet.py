"""Wallet analysis: gathers data, applies the rules, builds the report. No HTTP, no ML."""

import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.core.addresses import normalize_address
from app.engines.evidence import Evidence
from app.engines.report import build_report
from app.engines.wallet_rules import (
    code_evidence,
    counterparty_evidence,
    goplus_evidence,
    history_evidence,
    subject_intel_evidence,
)
from app.services.contract_data import get_contract_data
from app.services.coverage import CoverageItem, from_section, translate_status
from app.services.intel_lookup import IntelLookup, intel_coverage
from app.services.wallet_data import WalletHistory, get_wallet_history

logger = logging.getLogger("chainguard.engine.wallet")

MAX_COUNTERPARTIES = 2000


def _counterparties(history: WalletHistory, subject: str) -> list[str]:
    seen: Counter[str] = Counter()
    for t in history.transactions.items:
        for a in (t.from_address, t.to_address):
            if a:
                seen[a.lower()] += 1
    for t in history.token_transfers.items:
        for a in (t.from_address, t.to_address):
            if a:
                seen[a.lower()] += 1
    seen.pop(subject, None)
    return [a for a, _ in seen.most_common(MAX_COUNTERPARTIES)]


def analyze_wallet(
    chain_id: int,
    address: str,
    *,
    history_provider: Any,
    rpc: Any,
    explorer: Any,
    goplus: Any,
    intel_lookup: Callable[[int, list[str]], IntelLookup],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    addr = normalize_address(address)

    history = get_wallet_history(history_provider, chain_id, addr)
    contract = get_contract_data(rpc, explorer, goplus, chain_id, addr)
    gp = goplus.address_security(chain_id, addr)
    counterparties = _counterparties(history, addr)

    lookup: IntelLookup | None = None
    try:
        lookup = intel_lookup(chain_id, [addr, *counterparties])
    except Exception as exc:
        logger.warning("intel lookup failed", extra={"extra_fields": {"error_class": type(exc).__name__}})

    gp_status, gp_detail = translate_status(gp.status, gp.detail)
    coverage = [
        from_section(contract.bytecode, required=True),
        from_section(history.transactions, required=True),
        from_section(history.token_transfers),
        from_section(history.first_transaction),
        CoverageItem("goplus_address", gp_status, gp.provider, gp_detail, True),
        intel_coverage(lookup),
    ]

    evidence: list[Evidence] = []
    if lookup is not None:
        evidence += subject_intel_evidence(lookup.hits.get(addr, ()))
        evidence += counterparty_evidence({a: h for a, h in lookup.hits.items() if a != addr})
    evidence += goplus_evidence(gp)
    evidence += code_evidence(contract)
    evidence += history_evidence(history, now)

    sources: list[tuple[str | None, datetime | None]] = [
        (history.transactions.source, history.transactions.fetched_at),
        (contract.bytecode.source, contract.bytecode.fetched_at),
        (gp.provider, gp.fetched_at),
    ]
    if lookup is not None:
        sources += [(s.name, s.last_fetched_at) for s in lookup.sources]

    return build_report(
        chain_id=chain_id,
        subject_type="wallet",
        subject_key=addr,
        evidence=evidence,
        coverage=coverage,
        data_sources=sources,
        now=now,
    )
