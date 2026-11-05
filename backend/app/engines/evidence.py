"""Evidence objects and the risk-level decision (API_SPEC.md risk rules). No I/O.

Each piece of evidence maps to a level:
  info -> none; low, moderate -> MODERATE;
  high -> HIGH if verified, else MODERATE;
  critical -> CRITICAL if verified, else HIGH.
The overall level is the highest of these, so a verified critical or high finding is a floor.
With no findings, LOW needs at least one required check and every required check completed
(partial does not count). Otherwise the answer is INSUFFICIENT_DATA. Nothing is called safe.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.services.coverage import CoverageItem, required_checks_completed

Severity = Literal["info", "low", "moderate", "high", "critical"]
Kind = Literal["rule", "ml", "intel", "provider"]
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA"]

_ORDER = ["MODERATE", "HIGH", "CRITICAL"]


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: Kind
    claim: str
    severity: Severity
    confidence: float
    verified: bool
    data: dict[str, Any]
    source: str
    fetched_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "claim": self.claim,
            "severity": self.severity,
            "confidence": self.confidence,
            "verified": self.verified,
            "data": self.data,
            "source": {
                "name": self.source,
                "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            },
        }


def evidence_level(e: Evidence) -> str | None:
    if e.severity == "info":
        return None
    if e.severity == "critical":
        return "CRITICAL" if e.verified else "HIGH"
    if e.severity == "high":
        return "HIGH" if e.verified else "MODERATE"
    return "MODERATE"


def decide_level(evidence: Iterable[Evidence], coverage: Iterable[CoverageItem]) -> RiskLevel:
    levels = [lv for lv in (evidence_level(e) for e in evidence) if lv]
    if levels:
        return max(levels, key=_ORDER.index)  # type: ignore[return-value]
    coverage = list(coverage)
    if not any(i.required for i in coverage) or not required_checks_completed(coverage):
        return "INSUFFICIENT_DATA"
    return "LOW"
