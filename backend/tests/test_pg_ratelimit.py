from uuid import uuid4

from app.core import pg_ratelimit
from app.core.pg_ratelimit import PgTokenBucket


def _bucket(name=None, capacity=2):
    return PgTokenBucket(capacity=capacity, refill_per_second=0.001, name=name or f"t{uuid4().hex}")


def test_allows_up_to_capacity_then_blocks():
    b = _bucket()
    try:
        assert b.allow("k")[0] is True
        assert b.allow("k")[0] is True
        allowed, retry = b.allow("k")
        assert allowed is False
        assert retry > 0
    finally:
        b.reset()


def test_keys_are_independent():
    b = _bucket(capacity=1)
    try:
        assert b.allow("a")[0] is True
        assert b.allow("a")[0] is False
        assert b.allow("b")[0] is True
    finally:
        b.reset()


def test_state_is_shared_between_instances():
    """Two instances with the same name model two workers sharing one database."""
    name = f"t{uuid4().hex}"
    first, second = _bucket(name), _bucket(name)
    try:
        assert first.allow("k")[0] is True
        assert first.allow("k")[0] is True
        assert second.allow("k")[0] is False
    finally:
        first.reset()


def test_falls_back_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(pg_ratelimit, "get_engine", lambda: None)
    b = _bucket(capacity=1)
    assert b.allow("k")[0] is True
    assert b.allow("k")[0] is False
