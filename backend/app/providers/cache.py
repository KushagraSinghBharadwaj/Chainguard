"""Provider response cache (raw responses only).

Stores what the provider returned, so a later code change never leaves unreadable rows
and the original fetched_at survives. Only "ok" and "not_found" are cacheable.
rate_limited and unavailable are never stored. The cache is best effort: any failure
here is logged by class name and treated as a miss.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import ProviderCache
from app.db.session import get_engine

logger = logging.getLogger("chainguard.cache")

ENVELOPE_VERSION = 1
CACHEABLE_STATUSES = frozenset({"ok", "not_found"})
FORBIDDEN_PARAM_NAMES = frozenset(
    {"apikey", "api_key", "key", "token", "secret", "password", "authorization", "x-api-key"}
)

# Initial guesses, not measured. Tune from real usage.
TTL_SECONDS: dict[str, int] = {
    "contract_source": 86_400,
    "contract_source_unverified": 3_600,
    "code": 300,
    "storage": 60,
    "eth_call": 600,
    "wallet_page": 300,
    "goplus_token": 3_600,
    "goplus_address": 1_800,
}
NOT_FOUND_TTL_SECONDS = 300


def _canonical_value(v: Any) -> Any:
    if isinstance(v, str) and v.startswith("0x"):
        return v.lower()
    return v


def build_cache_key(provider: str, chain_id: int, operation: str, params: dict[str, Any]) -> str:
    """provider:chain_id:operation:sha256(canonical params). Never accepts secret-like params."""
    for name in params:
        if str(name).lower() in FORBIDDEN_PARAM_NAMES:
            raise ValueError(f"param name not allowed in a cache key: {name}")
    canonical = json.dumps(
        {k: _canonical_value(v) for k, v in params.items()},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{provider}:{chain_id}:{operation}:{digest}"


def ttl_for(operation: str, *, found: bool = True) -> int:
    if not found:
        return NOT_FOUND_TTL_SECONDS
    try:
        return TTL_SECONDS[operation]
    except KeyError:
        raise ValueError(f"no TTL defined for operation: {operation}") from None


def make_envelope(status: str, raw: Any) -> dict[str, Any]:
    if status not in CACHEABLE_STATUSES:
        raise ValueError(f"status is never cached: {status}")
    if status == "not_found":
        return {"v": ENVELOPE_VERSION, "found": False}
    if raw is None:
        raise ValueError("an ok result needs a raw payload")
    return {"v": ENVELOPE_VERSION, "found": True, "raw": raw}


def read_envelope(payload: Any) -> tuple[bool, Any] | None:
    """Return (found, raw), or None if the row is not a valid current-version envelope."""
    if not isinstance(payload, dict) or payload.get("v") != ENVELOPE_VERSION:
        return None
    found = payload.get("found")
    if found is False:
        return False, None
    if found is True and "raw" in payload:
        return True, payload["raw"]
    return None


@dataclass(frozen=True)
class CacheHit:
    found: bool
    raw: Any
    fetched_at: datetime
    expires_at: datetime


def cache_get(session: Session, key: str, now: datetime | None = None) -> CacheHit | None:
    now = now or datetime.now(timezone.utc)
    try:
        row = session.execute(
            select(ProviderCache).where(ProviderCache.cache_key == key, ProviderCache.expires_at > now)
        ).scalar_one_or_none()
        if row is None:
            return None
        parsed = read_envelope(row.payload)
        if parsed is None:
            return None
        return CacheHit(parsed[0], parsed[1], row.fetched_at, row.expires_at)
    except Exception as exc:
        session.rollback()
        logger.warning("cache read failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
        return None


def cache_put(
    session: Session,
    key: str,
    provider: str,
    status: str,
    raw: Any,
    operation: str,
    fetched_at: datetime | None = None,
) -> bool:
    """Store a cacheable result. Returns False for anything not stored."""
    if status not in CACHEABLE_STATUSES:
        return False
    try:
        envelope = make_envelope(status, raw)
        fetched = fetched_at or datetime.now(timezone.utc)
        expires = fetched + timedelta(seconds=ttl_for(operation, found=envelope["found"]))
        stmt = insert(ProviderCache).values(
            cache_key=key, provider=provider, payload=envelope, fetched_at=fetched, expires_at=expires
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ProviderCache.cache_key],
            set_={"provider": provider, "payload": envelope, "fetched_at": fetched, "expires_at": expires},
        )
        session.execute(stmt)
        session.commit()
        return True
    except Exception as exc:
        session.rollback()
        logger.warning("cache write failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
        return False


def _default_session() -> Session | None:
    engine = get_engine()
    return Session(engine) if engine is not None else None


class ProviderCacheStore:
    # Best-effort cache for the adapters: one short-lived session per call.
    # No database, or any database error, behaves as a miss and a skipped write.

    def __init__(self, session_factory: Callable[[], Session | None] = _default_session) -> None:
        self._factory = session_factory

    def _open(self) -> Session | None:
        try:
            return self._factory()
        except Exception as exc:
            logger.warning("cache session failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
            return None

    def get(self, key: str) -> CacheHit | None:
        session = self._open()
        if session is None:
            return None
        with session:
            return cache_get(session, key)

    def put(
        self,
        key: str,
        provider: str,
        status: str,
        raw: Any,
        operation: str,
        fetched_at: datetime | None = None,
    ) -> bool:
        session = self._open()
        if session is None:
            return False
        with session:
            return cache_put(session, key, provider, status, raw, operation, fetched_at)
