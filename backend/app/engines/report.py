"""Builds the Report object from API_SPEC.md. Text is deterministic and built from evidence."""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.engines.evidence import Evidence, decide_level, evidence_level
from app.services.coverage import CoverageItem

ENGINE_VERSION = "wallet-rules-0.2"

_RANK = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "info": 0}

BASE_LIMITATIONS = (
    "Not appearing on a list does not mean an address is safe.",
    "Community phishing lists lag behind new scams, so very recent scam addresses can be missing.",
    "GoPlus lists ScamSniffer among its own sources, so those two are not independent evidence.",
    "No machine-learning model was used for this report.",
)

# First matching prefix wins, so the specific OFAC entry must come before the generic list entry.
_CONSEQUENCES = (
    ("intel.ofac", "Dealing with a sanctioned address can create legal and compliance problems, and services may freeze or refuse related funds."),
    ("intel.", "Funds sent to an address reported on a scam list are usually not recoverable."),
    ("provider.goplus", "Another security provider flags this address. Verify it independently before sending anything."),
    ("code.eip7702", "Code delegated to an account can run when the account is used. Check what the delegate contract does before trusting it."),
)


def _ranked(evidence: list[Evidence]) -> list[Evidence]:
    return sorted(evidence, key=lambda e: (-_RANK[e.severity], e.id))


def _summary(level: str, evidence: list[Evidence], coverage: list[CoverageItem]) -> str:
    if level == "INSUFFICIENT_DATA":
        missing = [i.check for i in coverage if i.required and i.status != "completed"]
        return (
            "Not enough data to assess this subject: required checks did not complete ("
            + ", ".join(missing or ["none defined"])
            + "). This is neither a finding of safety nor of risk."
        )
    if level == "LOW":
        return "No findings in the checks that completed. This is not a guarantee of safety; see limitations."
    claims = [e.claim for e in _ranked(evidence) if evidence_level(e)][:3]
    return f"{level} risk. " + " ".join(claims)


def _consequences(evidence: list[Evidence]) -> list[str]:
    out: list[str] = []
    for e in _ranked(evidence):
        if not evidence_level(e):
            continue
        for prefix, text in _CONSEQUENCES:
            if e.id.startswith(prefix):
                if text not in out:
                    out.append(text)
                break
    return out


def _coverage_limitations(coverage: list[CoverageItem]) -> list[str]:
    words = {"partial": "was only partly checked", "unavailable": "could not be checked", "skipped": "was skipped"}
    out = []
    for i in coverage:
        if i.status == "completed":
            continue
        detail = f" ({i.detail})" if i.detail else ""
        out.append(f"{i.check} {words[i.status]}{detail}.")
    return out


def build_report(
    *,
    chain_id: int,
    subject_type: str,
    subject_key: str,
    evidence: list[Evidence],
    coverage: list[CoverageItem],
    data_sources: list[tuple[str | None, datetime | None]],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    level = decide_level(evidence, coverage)
    latest: dict[str, datetime | None] = {}
    for name, fetched in data_sources:
        if not name:
            continue
        prev = latest.get(name)
        if name not in latest or (fetched is not None and (prev is None or fetched > prev)):
            latest[name] = fetched
    return {
        "report_id": str(uuid.uuid4()),
        "chain_id": chain_id,
        "subject": {"type": subject_type, "key": subject_key},
        "risk_level": level,
        "summary": _summary(level, evidence, coverage),
        "evidence": [e.to_api() for e in _ranked(evidence)],
        "coverage": [i.to_api() for i in coverage],
        "consequences": _consequences(evidence),
        "limitations": list(BASE_LIMITATIONS) + _coverage_limitations(coverage),
        "model": {"status": "unavailable", "version": None},
        "data_sources": [
            {"name": n, "fetched_at": f.isoformat() if f else None} for n, f in sorted(latest.items())
        ],
        "generated_at": now.isoformat(),
        "engine_version": ENGINE_VERSION,
    }
