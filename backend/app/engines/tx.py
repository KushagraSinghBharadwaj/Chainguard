"""Transaction analysis: decodes calldata, applies rules, builds the report. No signing, no ML."""

import logging
import time
from collections.abc import Iterator
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

# The real stages of analyze_transaction_steps, in the order they run.
STEPS = (
    ("contract_data", "fetch contract code, source and token security"),
    ("decode", "decode the call data"),
    ("intel", "look up sanctions and scam lists"),
    ("rules", "apply risk rules"),
)


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def analyze_transaction_steps(chain_id: int, to: str, data: str, *, rpc: Any, explorer: Any, goplus: Any,
                              intel_lookup: Any, now: datetime | None = None) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ("start", ...), then ("step", ...) events as each stage runs, then ("report", report)."""
    now = now or datetime.now(timezone.utc)
    yield "start", {"steps": [{"id": sid, "label": label} for sid, label in STEPS]}

    started = time.perf_counter()
    yield "step", {"id": "contract_data", "status": "running"}
    target = normalize_address(to)
    c = get_contract_data(rpc, explorer, goplus, chain_id, target)
    yield "step", {"id": "contract_data", "status": "done", "ms": _ms(started)}

    started = time.perf_counter()
    yield "step", {"id": "decode", "status": "running"}
    decoded = decode_calldata(data, abis_for_contract(c))
    yield "step", {"id": "decode", "status": "done", "ms": _ms(started)}

    started = time.perf_counter()
    yield "step", {"id": "intel", "status": "running"}
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
    yield "step", {"id": "intel", "status": "done" if lookup is not None else "unavailable", "ms": _ms(started)}

    started = time.perf_counter()
    yield "step", {"id": "rules", "status": "running"}
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
    report = build_report(
        chain_id=chain_id, subject_type="transaction", subject_key=target, evidence=evidence,
        coverage=coverage, data_sources=sources, now=now,
        engine_version=TX_ENGINE_VERSION, base_limitations=TX_LIMITATIONS,
    )
    yield "step", {"id": "rules", "status": "done", "ms": _ms(started)}
    yield "report", report


def analyze_transaction(chain_id: int, to: str, data: str, *, rpc: Any, explorer: Any, goplus: Any,
                        intel_lookup: Any, now: datetime | None = None) -> dict[str, Any]:
    report = None
    for kind, payload in analyze_transaction_steps(
        chain_id, to, data, rpc=rpc, explorer=explorer, goplus=goplus, intel_lookup=intel_lookup, now=now
    ):
        if kind == "report":
            report = payload
    return report