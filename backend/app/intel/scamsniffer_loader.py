from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.db.models import IntelEntry, IntelSource
from app.db.session import get_engine
from app.intel.scamsniffer import ScamSnifferParseResult, parse_scamsniffer

SOURCE_NAME = "scamsniffer"
REPO_URL = "https://github.com/scamsniffer/scam-database"
_RAW = "https://raw.githubusercontent.com/scamsniffer/scam-database/main"
DATA_URL = f"{_RAW}/blacklist/all.json"
LICENSE_URL = f"{_RAW}/LICENSE"
CATEGORY = "phishing"
MAX_BYTES = 25 * 1024 * 1024
MIN_RATIO = 0.5  # refuse to replace the table if the new list is under half the old one


def _download(url: str) -> bytes:
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError(f"download from {url} exceeds {MAX_BYTES} bytes")
    return response.content


def license_summary(text: str) -> str:
    """First lines of the LICENSE file; refuse anything that is not a GNU GPL."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = " ".join(lines[:2])
    if "GNU GENERAL PUBLIC LICENSE" not in head.upper():
        raise ValueError(f"license not recognised as GNU GPL, review before loading: {head[:120]!r}")
    return head


def load_entries(
    engine,
    result: ScamSnifferParseResult,
    *,
    license_note: str,
    version_label: str,
    fetched_at: datetime,
    source_name: str = SOURCE_NAME,
    url: str = REPO_URL,
) -> int:
    """Replace the source's rows in one transaction. Any error rolls everything back."""
    if not result.addresses:
        raise ValueError("refusing to load: no valid addresses parsed")
    with Session(engine) as session, session.begin():
        source = session.execute(
            select(IntelSource).where(IntelSource.name == source_name)
        ).scalar_one_or_none()
        if source is None:
            source = IntelSource(name=source_name)
            session.add(source)
            session.flush()
        existing = session.execute(
            select(func.count()).select_from(IntelEntry).where(IntelEntry.source_id == source.id)
        ).scalar_one()
        if existing and len(result.addresses) < existing * MIN_RATIO:
            raise ValueError(
                f"refusing to replace {existing} rows with {len(result.addresses)}: "
                "new list is under 50% of the existing one"
            )
        session.execute(delete(IntelEntry).where(IntelEntry.source_id == source.id))
        session.execute(
            insert(IntelEntry),
            [
                {
                    "source_id": source.id,
                    "chain_id": None,  # EVM-wide: not tied to one chain
                    "address": address,
                    "domain": None,
                    "category": CATEGORY,
                    "label": None,
                    "fetched_at": fetched_at,
                }
                for address in result.addresses
            ],
        )
        source.url = url
        source.license_note = license_note
        source.version_label = version_label
        source.last_fetched_at = fetched_at
    return len(result.addresses)


def main() -> int:
    fetched_at = datetime.now(timezone.utc)
    lic = license_summary(_download(LICENSE_URL).decode("utf-8", "replace"))
    result = parse_scamsniffer(_download(DATA_URL))
    note = (
        f"{lic}. Source: {REPO_URL} (LICENSE file read {fetched_at.date()}). "
        "Upstream list is published with a 7-day delay. "
        "Server-side use only: do not bundle or redistribute the list."
    )
    version = f"{fetched_at.date().isoformat()} (upstream 7-day delay)"
    loaded = load_entries(
        get_engine(), result, license_note=note, version_label=version, fetched_at=fetched_at
    )
    print("license read from repo:", lic)
    print(f"rows seen: {result.rows_seen}")
    print(f"loaded (unique, valid): {loaded}")
    print(f"rejected non-EVM: {result.non_evm}, invalid: {result.invalid}, duplicates: {result.duplicates}")
    print("rejected samples:", list(result.rejected_samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
