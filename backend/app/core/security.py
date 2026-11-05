import hashlib
import secrets
from datetime import timedelta

TOKEN_TTL = timedelta(days=30)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hex digest. Only this hash is ever stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
