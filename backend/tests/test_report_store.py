"""Report store tests. Reports here are SYNTHETIC minimal dicts with a fake address."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.report_store import DEGRADED_TTL, FULL_TTL, get_fresh, save, ttl_for

KEY = "0x" + "b" * 40


def make(level="LOW", statuses=("completed",), version="test-engine-1"):
    return {
        "report_id": str(uuid.uuid4()),
        "chain_id": 1,
        "subject": {"type": "wallet", "key": KEY},
        "risk_level": level,
        "coverage": [{"check": "x", "status": s, "source": "s", "detail": None} for s in statuses],
        "model": {"status": "unavailable", "version": None},
        "engine_version": version,
    }


@pytest.fixture
def db():
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM analysis_reports WHERE subject_key = :k"), {"k": KEY})
    with Session(get_engine()) as session:
        yield session
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM analysis_reports WHERE subject_key = :k"), {"k": KEY})


def test_clean_report_gets_the_full_ttl():
    assert ttl_for(make()) == FULL_TTL


@pytest.mark.parametrize("status", ["partial", "unavailable"])
def test_degraded_coverage_gets_the_short_ttl(status):
    assert ttl_for(make(statuses=("completed", status))) == DEGRADED_TTL


def test_insufficient_data_gets_the_short_ttl():
    assert ttl_for(make(level="INSUFFICIENT_DATA")) == DEGRADED_TTL


def test_nothing_stored_returns_none(db):
    assert get_fresh(db, 1, "wallet", KEY, "test-engine-1") is None


def test_saved_report_is_returned_and_key_is_case_insensitive(db):
    r = make()
    save(db, r)
    assert get_fresh(db, 1, "wallet", KEY, "test-engine-1")["report_id"] == r["report_id"]
    assert get_fresh(db, 1, "wallet", "0x" + "B" * 40, "test-engine-1") is not None


def test_expired_report_is_ignored(db):
    save(db, make())
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE analysis_reports SET expires_at = :t WHERE subject_key = :k"),
            {"t": datetime.now(timezone.utc) - timedelta(minutes=1), "k": KEY},
        )
    assert get_fresh(db, 1, "wallet", KEY, "test-engine-1") is None


def test_other_engine_version_is_ignored(db):
    save(db, make(version="test-engine-1"))
    assert get_fresh(db, 1, "wallet", KEY, "test-engine-2") is None


def test_stored_expiry_matches_the_ttl_rule(db):
    save(db, make(statuses=("partial",)))
    with get_engine().connect() as conn:
        seconds = conn.execute(
            text("SELECT extract(epoch FROM expires_at - created_at) FROM analysis_reports WHERE subject_key = :k"),
            {"k": KEY},
        ).scalar()
    assert abs(float(seconds) - DEGRADED_TTL.total_seconds()) < 5
