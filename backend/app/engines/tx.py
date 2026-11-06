"""Transaction analysis: decodes calldata, applies rules, builds the report. No signing, no ML."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.addresses import normalize_address
from app.engines.report import build_report
from app.engines.tx_rules import call_evidence, recipient_of, spender_of, target_evidence
from app.engines.wallet_rules import subject_intel_evidence
from app.services.calldata import abis_for_contract, decode_calldata
from app.services.contract_data import get_contract_data
from app.services.coverage import from_section
from app.services.intel_lookup import intel_coverage

logger = logging.getLogger("chainguard.engine.tx")

TX_ENGINE_VERSION = "tx-rules-0.1"
TX_LIMITATIONS = (
    "This analysis reads calldata only. Nothing was signed, sent or simulated.",
    "No loss estimate was made. Real effects can differ from what the calldata suggests.",
    "Not appearing on a list does not mean an address is safe.",
    "A call that could not be decoded is unknown, not safe.",
    "No machine-learning model was used for this report.",
)


def analyze_transaction(chain_id: int, to: str, data: str, *, rpc: Any, explorer: Any, goplus: Any,
                        intel_lookup: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    target = normalize_address(to)
    c = get_contract_data(rpc, explorer, goplus, chain_id, target)
    decoded = decode_calldata(data, abis_for_contract(c))

    related = {target}
    for fn in (spender_of, recipient_of):
        a = fn(decoded)
        if a:
            try:
                related.add(normalize_address(a))
            except Exception:
                pass
    lookup = None
    try:
        lookup = intel_lookup(chain_id, sorted(related))
    except Exception as exc:
        logger.warning("intel lookup failed", extra={"extra_fields": {"error_class": type(exc).__name__}})

    evidence = call_evidence(decoded, now) + target_evidence(c.bytecode, c.source, now)
    if lookup is not None:
        for addr in sorted(related):
            evidence += subject_intel_evidence(lookup.hits.get(addr, ()))

    coverage = [
        from_section(c.bytecode, required=True),
        from_section(c.source),
        from_section(c.implementation_source),
        intel_coverage(lookup),
    ]
    sources = [(c.bytecode.source, c.bytecode.fetched_at)]
    if lookup is not None:
        sources += [(s.name, s.last_fetched_at) for s in lookup.sources]
    return build_report(
        chain_id=chain_id, subject_type="transaction", subject_key=target, evidence=evidence,
        coverage=coverage, data_sources=sources, now=now,
        engine_version=TX_ENGINE_VERSION, base_limitations=TX_LIMITATIONS,
    )
