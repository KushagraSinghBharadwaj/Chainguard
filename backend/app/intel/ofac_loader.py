import logging
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from sqlalchemy import func, insert, select, delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import IntelEntry, IntelSource
from app.db.session import get_engine
from app.intel.ofac import OfacParseResult, parse_sdn_advanced
from app.providers.base import ProviderResult, ResultStatus

logger = logging.getLogger("chainguard.intel.ofac")

PROVIDER = "ofac"
SOURCE_NAME = "ofac_sdn"
CATEGORY = "sanctions"
ETHEREUM_CHAIN_ID = 1
SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML"
MAX_BYTES = 400 * 1024 * 1024


def _fail(status: ResultStatus, detail: str, retry: bool) -> tuple[ProviderResult[Path], bool]:
    return ProviderResult(status, PROVIDER, None, detail), retry


def _attempt(http: httpx.Client, url: str, dest: Path, max_bytes: int) -> tuple[ProviderResult[Path], bool]:
    try:
        with http.stream("GET", url) as resp:
            code = resp.status_code
            if code == 429:
                return _fail("rate_limited", "http_429", True)
            if code >= 500:
                return _fail("unavailable", f"http_{code}", True)
            if code != 200:
                return _fail("unavailable", f"http_{code}", False)
            written = 0
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(65536):
                    if written == 0 and b"<?xml" not in chunk[:64]:
                        return _fail("unavailable", "unexpected_content", False)
                    written += len(chunk)
                    if written > max_bytes:
                        return _fail("unavailable", "too_large", False)
                    fh.write(chunk)
            if written == 0:
                return _fail("unavailable", "empty_response", False)
    except httpx.HTTPError as exc:
        return _fail("unavailable", type(exc).__name__, True)
    return ProviderResult("ok", PROVIDER, dest, None), False


def download_sdn(
    dest: Path,
    *,
    url: str = SDN_URL,
    client: httpx.Client | None = None,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    max_bytes: int = MAX_BYTES,
) -> ProviderResult[Path]:
    """Stream the SDN file to dest. Failures are typed results; a partial file is never left behind."""
    own = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(10.0, read=60.0), follow_redirects=True)
    result: ProviderResult[Path] = ProviderResult("unavailable", PROVIDER, None, "no_attempt")
    try:
        for attempt in range(1, max_attempts + 1):
            result, retry = _attempt(http, url, dest, max_bytes)
            if result.status == "ok" or not retry or attempt == max_attempts:
                break
            sleep(backoff_seconds * attempt)
    finally:
        if own:
            http.close()
    if result.status != "ok":
        dest.unlink(missing_ok=True)
        logger.warning(
            "intel download failed",
            extra={"extra_fields": {"provider": PROVIDER, "status": result.status, "detail": result.detail}},
        )
    return result


@dataclass(frozen=True)
class LoadSummary:
    status: Literal["loaded", "refused", "failed"]
    detail: str | None = None
    inserted: int = 0
    removed: int = 0
    published: date | None = None
    rejected: int = 0
    other_0x_rows: dict[str, int] = field(default_factory=dict)


def load_ofac(
    session: Session,
    parsed: OfacParseResult,
    *,
    source_url: str,
    source_name: str = SOURCE_NAME,
    fetched_at: datetime | None = None,
    min_keep_ratio: float = 0.5,
) -> LoadSummary:
    """Replace the source's rows in one transaction. Refuses suspicious input and keeps old rows."""
    now = fetched_at or datetime.now(timezone.utc)
    stats = {"published": parsed.published, "rejected": parsed.rejected, "other_0x_rows": dict(parsed.other_0x_rows)}
    with session.begin():
        src = session.scalar(select(IntelSource).where(IntelSource.name == source_name))
        existing = 0
        if src is not None:
            existing = session.scalar(
                select(func.count()).select_from(IntelEntry).where(IntelEntry.source_id == src.id)
            ) or 0
        if not parsed.entries:
            return LoadSummary("refused", "no_entries_parsed", 0, 0, **stats)
        if existing and len(parsed.entries) < existing * min_keep_ratio:
            return LoadSummary("refused", "entry_count_dropped_sharply", 0, 0, **stats)
        if src is None:
            src = IntelSource(name=source_name)
            session.add(src)
            session.flush()
        session.execute(delete(IntelEntry).where(IntelEntry.source_id == src.id))
        rows = [
            {
                "source_id": src.id,
                "chain_id": ETHEREUM_CHAIN_ID,
                "address": e.address,
                "domain": None,
                "category": CATEGORY,
                "label": e.label,
                "fetched_at": now,
            }
            for e in parsed.entries
        ]
        session.execute(insert(IntelEntry), rows)
        src.url = source_url
        src.version_label = parsed.published.isoformat() if parsed.published else None
        src.last_fetched_at = now
    return LoadSummary("loaded", None, len(rows), existing, **stats)


def run_ofac_refresh(
    engine: Engine | None = None,
    *,
    url: str = SDN_URL,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    source_name: str = SOURCE_NAME,
) -> LoadSummary:
    engine = engine or get_engine()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "sdn_advanced.xml"
        dl = download_sdn(dest, url=url, client=client, sleep=sleep)
        if dl.status != "ok":
            return LoadSummary("failed", f"download_{dl.status}:{dl.detail}")
        try:
            parsed = parse_sdn_advanced(dest)
        except ET.ParseError:
            return LoadSummary("failed", "parse_error")
        with Session(engine) as session:
            return load_ofac(session, parsed, source_url=url, source_name=source_name)


if __name__ == "__main__":
    summary = run_ofac_refresh()
    print("status:", summary.status, "| detail:", summary.detail)
    print("inserted:", summary.inserted, "| removed:", summary.removed)
    print("published:", summary.published, "| rejected:", summary.rejected)
    print("other 0x rows not loaded:", summary.other_0x_rows)
    raise SystemExit(0 if summary.status == "loaded" else 1)
