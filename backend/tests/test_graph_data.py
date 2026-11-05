"""Graph fetcher tests. All data is SYNTHETIC: fake addresses, invented transfers, a fake provider."""

from datetime import datetime, timezone

from app.providers.base import ProviderResult, Transaction
from app.services.graph_data import collect_neighbor_graph

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
ME = "0x" + "a" * 40


def addr(n):
    return "0x" + f"{n:040x}"


def tx(i, frm, to, value=1):
    return Transaction(f"0x{i:064x}", i, NOW, frm, to, value, False, None, 21000)


class FakeProvider:
    def __init__(self, data=None, fail=(), rate_limit_at=None):
        self.data = data or {}
        self.fail = set(fail)
        self.rate_limit_at = rate_limit_at
        self.calls = []

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        self.calls.append(address)
        if self.rate_limit_at is not None and len(self.calls) >= self.rate_limit_at:
            return ProviderResult("rate_limited", "etherscan", None, "rate_limited")
        if address in self.fail:
            return ProviderResult("unavailable", "etherscan", None, "http_500")
        return ProviderResult("ok", "etherscan", self.data.get(address, []))


def subject_txs(n):
    return [tx(i, ME, addr(i), value=i) for i in range(1, n + 1)]


def test_calls_never_exceed_the_budget_and_status_is_partial():
    p = FakeProvider()
    g = collect_neighbor_graph(p, 1, ME, subject_txs(20), max_calls=5)
    assert len(p.calls) == 5 and g.calls_made == 5
    assert g.status == "partial" and "call_budget" in g.detail
    assert g.neighbors_total == 20 and g.neighbors_expanded == 5


def test_highest_value_neighbors_are_expanded_first():
    p = FakeProvider()
    collect_neighbor_graph(p, 1, ME, subject_txs(20), max_calls=3)
    assert p.calls == [addr(20), addr(19), addr(18)]


def test_all_neighbors_expanded_within_budget_is_completed():
    p = FakeProvider()
    g = collect_neighbor_graph(p, 1, ME, subject_txs(3), max_calls=8)
    assert g.status == "completed" and g.detail is None and g.searched_hops == 2


def test_one_failing_call_is_partial_and_keeps_the_other_data():
    extra = tx(900, addr(2), addr(77))
    p = FakeProvider(data={addr(2): [extra]}, fail=[addr(3)])
    g = collect_neighbor_graph(p, 1, ME, subject_txs(3))
    assert g.status == "partial" and "provider_failure" in g.detail
    assert any(t.hash == extra.hash for t in g.transactions)


def test_all_calls_failing_is_unavailable_not_clean():
    p = FakeProvider(fail=[addr(1), addr(2)])
    g = collect_neighbor_graph(p, 1, ME, subject_txs(2))
    assert g.status == "unavailable" and g.searched_hops == 1


def test_no_neighbors_is_skipped_and_makes_no_calls():
    p = FakeProvider()
    g = collect_neighbor_graph(p, 1, ME, [])
    assert g.status == "skipped" and p.calls == []


def test_full_page_from_a_neighbor_is_flagged_as_truncated():
    full = [tx(1000 + i, addr(1), addr(500 + i)) for i in range(100)]
    g = collect_neighbor_graph(FakeProvider(data={addr(1): full}), 1, ME, subject_txs(1))
    assert g.status == "partial" and "neighbor_history_truncated" in g.detail


def test_rate_limit_stops_further_calls():
    p = FakeProvider(rate_limit_at=2)
    g = collect_neighbor_graph(p, 1, ME, subject_txs(10), max_calls=8)
    assert len(p.calls) == 2 and g.status == "partial" and "rate_limited" in g.detail


def test_duplicate_transactions_are_not_repeated():
    shared = tx(1, ME, addr(1), value=1)
    g = collect_neighbor_graph(FakeProvider(data={addr(1): [shared]}), 1, ME, [shared])
    assert len(g.transactions) == 1
