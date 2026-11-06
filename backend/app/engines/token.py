"""Token analysis: gathers data, applies token rules, builds the report. No HTTP, no ML."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.addresses import normalize_address
from app.engines.evidence import Evidence
from app.engines.report import build_report
from app.engines.token_rules import goplus_token_evidence, owner_evidence, privilege_evidence, proxy_evidence
from app.engines.wallet_rules import subject_intel_evidence
from app.providers.base import ProviderResult
from app.services.contract_data import get_contract_data
from app.services.coverage import from_section
from app.services.intel_lookup import intel_coverage

logger = logging.getLogger("chainguard.engine.token")

TOKEN_ENGINE_VERSION = "token-rules-0.3"
TOKEN_LIMITATIONS = (
    "Not appearing on a list or in GoPlus does not mean a token is safe.",
    "Token flags come from GoPlus, a third party. They are not verified here.",
    "Owner powers were read from the verified ABI only. Upgrade admin and liquidity were not checked. Renounced status comes from owner() only.",
    "No transaction simulation was run, so a honeypot that GoPlus has not flagged can be missed.",
    "No machine-learning model was used for this report.",
)


def analyze_token(chain_id: int, address: str, *, rpc: Any, explorer: Any, goplus: Any, intel_lookup: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    addr = normalize_address(address)
    c = get_contract_data(rpc, explorer, goplus, chain_id, addr)
    lookup = None
    try:
        lookup = intel_lookup(chain_id, [addr])
    except Exception as exc:
        logger.warning("intel lookup failed", extra={"extra_fields": {"error_class": type(exc).__name__}})

    evidence: list[Evidence] = []
    if lookup is not None:
        evidence += subject_intel_evidence(lookup.hits.get(addr, ()))
    if c.token.status == "ok" and c.token.data is not None:
        evidence += goplus_token_evidence(ProviderResult("ok", c.token.source or "goplus", c.token.data, None, c.token.fetched_at))
    evidence += proxy_evidence(c.proxy)
    evidence += privilege_evidence(c.source, c.implementation_source)
    owner_res = None
    if c.bytecode.status == "ok" and c.bytecode.data is not None and c.bytecode.data.kind == "contract":
        try:
            owner_res = rpc.eth_call(chain_id, addr, "0x8da5cb5b")
        except Exception as exc:
            logger.warning("owner call failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
    evidence += owner_evidence(owner_res)

    coverage = [
        from_section(c.bytecode, required=True),
        from_section(c.source),
        from_section(c.proxy),
        from_section(c.implementation_source),
        from_section(c.token, required=True),
        intel_coverage(lookup),
    ]
    sources = [(c.bytecode.source, c.bytecode.fetched_at), (c.token.source, c.token.fetched_at)]
    if lookup is not None:
        sources += [(s.name, s.last_fetched_at) for s in lookup.sources]
    return build_report(
        chain_id=chain_id, subject_type="token", subject_key=addr, evidence=evidence,
        coverage=coverage, data_sources=sources, now=now,
        engine_version=TOKEN_ENGINE_VERSION, base_limitations=TOKEN_LIMITATIONS,
    )
