import math
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clientip import client_ip
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import TokenBucket
from app.core.security import hash_token
from app.db.models import Client, ClientToken
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)

_settings = get_settings()

# Limits for all authenticated /v1 routes. Registration has its own limiter in clients.py.
token_limiter = TokenBucket(
    capacity=_settings.rate_limit_token_burst,
    refill_per_second=_settings.rate_limit_token_per_minute / 60,
)
ip_limiter = TokenBucket(
    capacity=_settings.rate_limit_ip_burst,
    refill_per_second=_settings.rate_limit_ip_per_minute / 60,
)


def reset_limiters() -> None:
    token_limiter.reset()
    ip_limiter.reset()


@dataclass(frozen=True)
class AuthContext:
    client_id: UUID
    token_id: UUID


def _unauthenticated() -> ApiError:
    return ApiError(
        401,
        "unauthenticated",
        "Missing, invalid, expired or revoked token.",
        {"WWW-Authenticate": "Bearer"},
    )


def _rate_limited(retry_after: float) -> ApiError:
    return ApiError(
        429,
        "rate_limited",
        "Too many requests. Try again later.",
        {"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def require_client(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    # Per-IP limit first: it also protects the database from floods of bad tokens.
    allowed, retry = ip_limiter.allow(client_ip(request, _settings.trust_proxy_headers))
    if not allowed:
        raise _rate_limited(retry)

    if creds is None:
        raise _unauthenticated()
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(ClientToken, Client)
        .join(Client, Client.id == ClientToken.client_id)
        .where(
            ClientToken.token_hash == hash_token(creds.credentials),
            ClientToken.revoked_at.is_(None),
            ClientToken.expires_at > now,
            Client.revoked_at.is_(None),
        )
    ).first()
    if row is None:
        raise _unauthenticated()
    token, client = row

    # Per-token limit after authentication; a limited request does no database write.
    allowed, retry = token_limiter.allow(str(token.id))
    if not allowed:
        raise _rate_limited(retry)

    ctx = AuthContext(client_id=client.id, token_id=token.id)
    client.last_seen_at = now
    db.commit()
    return ctx
