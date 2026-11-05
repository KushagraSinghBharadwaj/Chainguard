"""Coverage model: which checks completed, which were partial, unavailable or skipped.

Services keep their own status words. This module translates them in one place into the
four words API_SPEC.md uses. An unknown status fails closed as "unavailable".
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

CoverageStatus = Literal["completed", "partial", "unavailable", "skipped"]
OverallStatus = Literal["complete", "partial"]

_STATUS_MAP: dict[str, CoverageStatus] = {
    "ok": "completed",
    "complete": "completed",
    "completed": "completed",
    "not_found": "completed",
    "partial": "partial",
    "rate_limited": "unavailable",
    "unavailable": "unavailable",
    "skipped": "skipped",
}


@dataclass(frozen=True)
class CoverageItem:
    check: str
    status: CoverageStatus
    source: str | None
    detail: str | None
    required: bool = False

    def to_api(self) -> dict[str, Any]:
        return {"check": self.check, "status": self.status, "source": self.source, "detail": self.detail}


def translate_status(raw: str, detail: str | None) -> tuple[CoverageStatus, str | None]:
    status = _STATUS_MAP.get(raw)
    if status is None:
        return "unavailable", "unknown_status"
    if raw == "rate_limited":
        return status, "rate_limited"
    if raw == "not_found":
        return status, detail or "not_found"
    if status == "partial":
        return status, detail or "incomplete"
    return status, detail


def from_section(section: Any, *, required: bool = False) -> CoverageItem:
    status, detail = translate_status(section.status, section.detail)
    stop = getattr(section, "stop_reason", None)
    if status == "partial" and stop:
        detail = stop if detail == "incomplete" else f"{stop}:{detail}"
    return CoverageItem(section.check, status, section.source, detail, required)


def required_checks_completed(items: Iterable[CoverageItem]) -> bool:
    return all(i.status == "completed" for i in items if i.required)


def overall_status(items: Iterable[CoverageItem]) -> OverallStatus:
    items = list(items)
    if not items:
        return "partial"
    for i in items:
        if i.status == "completed":
            continue
        if i.status == "skipped" and not i.required:
            continue
        return "partial"
    return "complete"
