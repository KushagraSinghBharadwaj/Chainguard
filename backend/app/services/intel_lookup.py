"""Looks up addresses in the locally stored OFAC and ScamSniffer data.

"No hits" is only meaningful if both lists are actually loaded, so coverage reports a list
that has never been fetched as partial, never as a clean result.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IntelEntry, IntelSource
from app.services.coverage import CoverageItem

EXPECTED_SOURCES = ("ofac", "scamsniffer")
CHUNK = 1000


@dataclass(frozen=True)
class IntelHit:
    source: str
    category: str
    label: str | None
    fetched_at: datetime | None
    list_version: str | None


@dataclass(frozen=True)
class IntelSourceInfo:
    name: str
    version_label: str | None
    last_fetched_at: datetime | None


@dataclass(frozen=True)
class IntelLookup:
    hits: dict[str, tuple[IntelHit, ...]]
    sources: tuple[IntelSourceInfo, ...]


def lookup_intel(session: Session, chain_id: int, addresses: list[str]) -> IntelLookup:
    addrs = sorted({a.lower() for a in addresses})
    hits: dict[str, list[IntelHit]] = {}
    for i in range(0, len(addrs), CHUNK):
        rows = session.execute(
            select(IntelEntry, IntelSource)
            .join(IntelSource, IntelSource.id == IntelEntry.source_id)
            .where(
                IntelEntry.address.in_(addrs[i : i + CHUNK]),
                or_(IntelEntry.chain_id == chain_id, IntelEntry.chain_id.is_(None)),
            )
        ).all()
        for entry, source in rows:
            hits.setdefault(entry.address, []).append(
                IntelHit(source.name, entry.category, entry.label, entry.fetched_at, source.version_label)
            )
    sources = session.execute(select(IntelSource).order_by(IntelSource.name)).scalars().all()
    return IntelLookup(
        {a: tuple(h) for a, h in hits.items()},
        tuple(IntelSourceInfo(s.name, s.version_label, s.last_fetched_at) for s in sources),
    )


def intel_coverage(lookup: IntelLookup | None) -> CoverageItem:
    if lookup is None:
        return CoverageItem("intel_lists", "unavailable", "chainguard_db", "database_error", True)
    loaded = [s.name.lower() for s in lookup.sources if s.last_fetched_at is not None]
    missing = [e for e in EXPECTED_SOURCES if not any(e in n for n in loaded)]
    if missing:
        return CoverageItem("intel_lists", "partial", "chainguard_db", "list_not_loaded:" + ",".join(missing), True)
    return CoverageItem("intel_lists", "completed", "chainguard_db", None, True)
