"""Collector tests. All data is SYNTHETIC: fake addresses, invented transfers, a fake provider."""

import json
from datetime import datetime, timezone

import pytest

from app.providers.base import ProviderResult, Transaction
from app.services import training_collect as tc
from app.services import training_store as ts

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
A = "0x" + "a" * 40
C1, C2, C3 = ("0x" + c * 40 for c in "123")


def tx(i, frm, to):
    return Transaction(f"0x{i:064x}", i, NOW, frm, to, 1, False, None, 21000)


class Fake:
    def __init__(self, txs, broken=False):
        self.txs = txs
        self.broken = broken
        self.calls = 0

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        self.calls += 1
        if self.broken:
            return ProviderResult("unavailable", "etherscan", None, "http_500")
        if not newest_first:
            return ProviderResult("ok", "etherscan", self.txs[-1:])
        return ProviderResult("ok", "etherscan", self.txs[(page - 1) * page_size : page * page_size])

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return ProviderResult("ok", "etherscan", [])


@pytest.fixture
def conn():
    c = ts.connect(":memory:")
    yield c
    c.close()


def test_collect_marks_done_and_stores_transactions(conn):
    ts.add_addresses(conn, 1, [A], "positive", "ofac_sdn")
    out = tc.collect_batch(conn, Fake([tx(1, A, C1), tx(2, C2, A)]), 1, 10)
    assert out == {"done": 1, "failed": 0}
    row = conn.execute("SELECT * FROM samples").fetchone()
    assert row["status"] == "done" and row["collected_at"]
    assert len(json.loads(row["raw_json"])["transactions"]) == 2


def test_provider_failure_is_not_stored_as_done(conn):
    ts.add_addresses(conn, 1, [A], "unlabeled", "x")
    out = tc.collect_batch(conn, Fake([], broken=True), 1, 10)
    assert out["done"] == 0 and out["failed"] == 1
    assert not any(k.endswith(":done") for k in ts.counts(conn))


def test_done_rows_are_not_fetched_again(conn):
    ts.add_addresses(conn, 1, [A], "positive", "ofac_sdn")
    p = Fake([tx(1, A, C1)])
    tc.collect_batch(conn, p, 1, 10)
    calls = p.calls
    assert tc.collect_batch(conn, p, 1, 10) == {"done": 0, "failed": 0}
    assert p.calls == calls


def test_sampling_excludes_listed_known_and_self_and_caps_per_source(conn):
    ts.add_addresses(conn, 1, [A, C2], "positive", "ofac_sdn")
    tc.collect_batch(conn, Fake([tx(1, A, C1), tx(2, A, C2), tx(3, A, C3), tx(4, C1, A)]), 1, 1)
    added = tc.sample_unlabeled(conn, 1, listed={C3}, n=10, per_source=2)
    got = {r["address"] for r in conn.execute("SELECT address FROM samples WHERE label = 'unlabeled'")}
    assert added == 1 and got == {C1}
