"""Token bucket stored in PostgreSQL so limits are shared by all workers and survive restarts.

Falls back to an in-process bucket when the database is unavailable, so a database
problem never turns into blocked users.
"""

import logging

from sqlalchemy import text

from app.core.ratelimit import TokenBucket
from app.db.session import get_engine

logger = logging.getLogger("chainguard.ratelimit")

_INSERT = text(
    "INSERT INTO rate_limits (key, tokens, updated_at) VALUES (:k, :cap, now()) "
    "ON CONFLICT (key) DO NOTHING"
)
_SELECT = text(
    "SELECT tokens, EXTRACT(EPOCH FROM (now() - updated_at)) "
    "FROM rate_limits WHERE key = :k FOR UPDATE"
)
_UPDATE = text("UPDATE rate_limits SET tokens = :t, updated_at = now() WHERE key = :k")


class PgTokenBucket:
    def __init__(self, capacity: int, refill_per_second: float, name: str = "bucket") -> None:
        self._capacity = float(capacity)
        self._rate = refill_per_second
        self._name = name
        self._fallback = TokenBucket(capacity, refill_per_second)

    def allow(self, key: str) -> tuple[bool, float]:
        engine = get_engine()
        if engine is None:
            return self._fallback.allow(key)
        k = f"{self._name}:{key}"
        try:
            with engine.begin() as conn:
                conn.execute(_INSERT, {"k": k, "cap": self._capacity})
                tokens, elapsed = conn.execute(_SELECT, {"k": k}).one()
                tokens = min(self._capacity, float(tokens) + max(0.0, float(elapsed)) * self._rate)
                if tokens >= 1:
                    new_tokens, allowed, retry = tokens - 1, True, 0.0
                else:
                    new_tokens, allowed, retry = tokens, False, (1 - tokens) / self._rate
                conn.execute(_UPDATE, {"k": k, "t": new_tokens})
            return allowed, retry
        except Exception as exc:
            logger.warning(
                "shared rate limit unavailable, using in-process limit",
                extra={"extra_fields": {"error_class": type(exc).__name__}},
            )
            return self._fallback.allow(key)

    def reset(self) -> None:
        self._fallback.reset()
        engine = get_engine()
        if engine is None:
            return
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM rate_limits WHERE key LIKE :p"),
                    {"p": self._name + ":%"},
                )
        except Exception as exc:
            logger.warning(
                "rate limit reset failed",
                extra={"extra_fields": {"error_class": type(exc).__name__}},
            )
