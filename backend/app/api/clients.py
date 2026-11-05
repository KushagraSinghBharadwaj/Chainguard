import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_client
from app.core.clientip import client_ip
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import TokenBucket
from app.core.security import TOKEN_TTL, hash_token, new_token
from app.db.models import Client, ClientToken
from app.db.session import get_db

router = APIRouter(prefix="/v1/clients", tags=["clients"])

# 5 registrations burst, refilling 5 per minute, per IP. The IP is never stored.
register_limiter = TokenBucket(capacity=5, refill_per_second=5 / 60)


class TokenResponse(BaseModel):
    client_id: UUID
    token: str
    expires_at: datetime


def _issue_token(db: Session, client_id: UUID) -> tuple[str, datetime]:
    token = new_token()
    expires_at = datetime.now(timezone.utc) + TOKEN_TTL
    db.add(
        ClientToken(
            client_id=client_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
    )
    return token, expires_at


@router.post("/register", response_model=TokenResponse)
def register(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request, get_settings().trust_proxy_headers)
    allowed, retry_after = register_limiter.allow(ip)
    if not allowed:
        raise ApiError(
            429,
            "rate_limited",
            "Too many registrations. Try again later.",
            {"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
    client = Client()
    db.add(client)
    db.flush()
    client_id = client.id
    token, expires_at = _issue_token(db, client_id)
    db.commit()
    return TokenResponse(client_id=client_id, token=token, expires_at=expires_at)


@router.post("/token/refresh", response_model=TokenResponse)
def refresh(
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
) -> TokenResponse:
    old = db.get(ClientToken, auth.token_id)
    if old is None:
        raise ApiError(401, "unauthenticated", "Missing, invalid, expired or revoked token.")
    old.revoked_at = datetime.now(timezone.utc)
    token, expires_at = _issue_token(db, auth.client_id)
    db.commit()
    return TokenResponse(client_id=auth.client_id, token=token, expires_at=expires_at)
