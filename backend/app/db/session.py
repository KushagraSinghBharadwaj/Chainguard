import logging
from functools import lru_cache
from typing import Literal

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError

logger = logging.getLogger("chainguard.db")

DatabaseStatus = Literal["ok", "unavailable", "not_configured"]


@lru_cache
def get_engine() -> Engine | None:
    """Return the shared engine, or None when DATABASE_URL is not set."""
    url = get_settings().database_url
    if url is None:
        return None
    return create_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def check_database() -> DatabaseStatus:
    """Run a real SELECT 1. Failures are reported explicitly, never as 'ok'."""
    try:
        engine = get_engine()
        if engine is None:
            return "not_configured"
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        # Error class only: the message can contain connection details.
        logger.warning(
            "database check failed",
            extra={"extra_fields": {"error_class": type(exc).__name__}},
        )
        return "unavailable"


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    engine = get_engine()
    if engine is None:
        raise ApiError(503, "database_unavailable", "Database is not configured.")
    with Session(engine) as session:
        yield session
