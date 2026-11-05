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
    added = tc.sample_unlabeled(conn, 1, listed={C3}, n=10, per_source=2, kind_of=lambda a: "wallet")
    got = {r["address"] for r in conn.execute("SELECT address FROM samples WHERE label = 'unlabeled'")}
    assert added == 1 and got == {C1}


class FakeRpc:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get_code(self, chain_id, address):
        self.calls.append(address)
        return self.answers[address]


def _history_conn(conn, *counterparties):
    ts.add_addresses(conn, 1, [A], "positive", "ofac_sdn")
    txs = [tx(i + 1, A, c) for i, c in enumerate(counterparties)]
    tc.collect_batch(conn, Fake(txs), 1, 1)


def test_contracts_and_unknown_are_excluded_from_the_unlabeled_sample(conn):
    _history_conn(conn, C1, C2, C3)
    kinds = {C1: "contract", C2: "unknown", C3: "wallet"}
    added = tc.sample_unlabeled(conn, 1, listed=set(), n=10, per_source=5, kind_of=kinds.__getitem__)
    got = {r["address"] for r in conn.execute("SELECT address FROM samples WHERE label = 'unlabeled'")}
    assert added == 1 and got == {C3}


def test_excluded_contracts_do_not_use_up_the_per_source_quota(conn):
    wallet = "0x" + "4" * 40
    _history_conn(conn, C1, C2, C3, wallet)
    kinds = {C1: "contract", C2: "contract", C3: "contract", wallet: "wallet"}
    added = tc.sample_unlabeled(conn, 1, listed=set(), n=10, per_source=1, kind_of=kinds.__getitem__)
    got = {r["address"] for r in conn.execute("SELECT address FROM samples WHERE label = 'unlabeled'")}
    assert added == 1 and got == {wallet}


def test_kind_lookup_classifies_code_and_caches_answers():
    rpc = FakeRpc(
        {
            C1: ProviderResult("ok", "alchemy", "0x"),
            C2: ProviderResult("ok", "alchemy", "0xef0100" + "ab" * 20),
            C3: ProviderResult("ok", "alchemy", "0x6080604052"),
        }
    )
    kind = tc.make_kind_lookup(rpc, 1)
    assert [kind(C1), kind(C2), kind(C3)] == ["wallet", "wallet", "contract"]
    kind(C3)
    assert rpc.calls == [C1, C2, C3]


def test_kind_lookup_never_guesses_when_the_provider_fails_and_does_not_cache_failures():
    rpc = FakeRpc({C1: ProviderResult("rate_limited", "alchemy", None, "rate_limited")})
    kind = tc.make_kind_lookup(rpc, 1)
    assert kind(C1) == "unknown"
    rpc.answers[C1] = ProviderResult("ok", "alchemy", "0x")
    assert kind(C1) == "wallet"
