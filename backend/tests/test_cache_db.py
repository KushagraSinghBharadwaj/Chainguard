import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.providers.cache import ProviderCacheStore, cache_get, cache_put

pytestmark = pytest.mark.skipif(get_engine() is None, reason="DATABASE_URL is not set")


@pytest.fixture
def key():
    k = "test:1:contract_source:" + uuid.uuid4().hex
    yield k
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM provider_cache WHERE cache_key = :k"), {"k": k})


def _count(k):
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT count(*) FROM provider_cache WHERE cache_key = :k"), {"k": k}).scalar()


def _now():
    return datetime.now(timezone.utc)


def test_stored_row_is_read_back_with_original_fetched_at(key):
    fetched = _now() - timedelta(seconds=100)
    raw = [{"SourceCode": "x", "ABI": "[]"}]
    with Session(get_engine()) as s:
        assert cache_put(s, key, "etherscan", "ok", raw, "contract_source", fetched) is True
    with Session(get_engine()) as s:
        hit = cache_get(s, key)
    assert hit is not None and hit.found is True and hit.raw == raw
    assert hit.fetched_at == fetched
    assert hit.expires_at == fetched + timedelta(seconds=86_400)


def test_expired_row_is_ignored(key):
    fetched = _now() - timedelta(days=2)
    with Session(get_engine()) as s:
        assert cache_put(s, key, "etherscan", "ok", {"a": 1}, "contract_source", fetched) is True
        assert cache_get(s, key) is None


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "skipped"])
def test_failure_is_never_stored(key, status):
    with Session(get_engine()) as s:
        assert cache_put(s, key, "etherscan", status, {"a": 1}, "contract_source") is False
        assert cache_get(s, key) is None
    assert _count(key) == 0


def test_not_found_is_stored_as_not_found_with_short_ttl(key):
    fetched = _now()
    with Session(get_engine()) as s:
        assert cache_put(s, key, "goplus", "not_found", None, "goplus_token", fetched) is True
        hit = cache_get(s, key)
    assert hit is not None and hit.found is False and hit.raw is None
    assert hit.expires_at == fetched + timedelta(seconds=300)


def test_second_put_replaces_the_first(key):
    with Session(get_engine()) as s:
        cache_put(s, key, "etherscan", "ok", {"v": 1}, "contract_source")
        cache_put(s, key, "etherscan", "ok", {"v": 2}, "contract_source")
        hit = cache_get(s, key)
    assert hit.raw == {"v": 2} and _count(key) == 1


def test_row_with_unknown_envelope_version_is_ignored(key):
    now = _now()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO provider_cache (cache_key, provider, payload, fetched_at, expires_at) "
                "VALUES (:k, 'etherscan', CAST(:p AS jsonb), :f, :e)"
            ),
            {"k": key, "p": json.dumps({"v": 99, "found": True, "raw": 1}), "f": now, "e": now + timedelta(hours=1)},
        )
    with Session(get_engine()) as s:
        assert cache_get(s, key) is None


def test_store_roundtrip_and_a_failed_write_does_not_evict_a_good_row(key):
    store = ProviderCacheStore(lambda: Session(get_engine()))
    assert store.put(key, "etherscan", "ok", {"a": 1}, "contract_source") is True
    assert store.put(key, "etherscan", "unavailable", None, "contract_source") is False
    hit = store.get(key)
    assert hit is not None and hit.raw == {"a": 1}


def test_store_without_a_database_is_a_miss_not_an_error():
    assert ProviderCacheStore(lambda: None).get("k") is None
    assert ProviderCacheStore(lambda: None).put("k", "p", "ok", {"a": 1}, "contract_source") is False

    def boom():
        raise RuntimeError("no database")

    broken = ProviderCacheStore(boom)
    assert broken.get("k") is None
    assert broken.put("k", "p", "ok", {"a": 1}, "contract_source") is False
