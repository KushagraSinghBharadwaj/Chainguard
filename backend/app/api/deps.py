from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import hash_token
from app.db.models import Client, ClientToken
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


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


def require_client(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
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
    ctx = AuthContext(client_id=client.id, token_id=token.id)
    client.last_seen_at = now
    db.commit()
    return ctx
