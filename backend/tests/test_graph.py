"""Graph signal tests. All data is SYNTHETIC: fake addresses and invented transfers."""

from datetime import datetime, timezone

from app.features.graph import compute_graph_signals
from app.providers.base import Transaction

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
ME = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40
X = "0x" + "e" * 40
Y = "0x" + "f" * 40
L = "0x" + "1" * 40  # stands in for a listed address


def tx(i, frm, to, value=1, err=False):
    return Transaction(f"0x{i:064x}", i, NOW, frm, to, value, err, None, 21000)


def sig(txs, listed=(), hops=2):
    return compute_graph_signals(txs, ME, set(listed), hops)


def test_failed_and_creation_transactions_add_no_edges():
    s = sig([tx(1, ME, B, err=True), tx(2, ME, None)])
    assert s.edge_count == 0


def test_listed_address_two_hops_away_is_found():
    s = sig([tx(1, ME, B), tx(2, B, L)], listed=[L])
    assert s.nearest_listed_address == L and s.hop_distance == 2


def test_incoming_link_counts_as_one_hop():
    s = sig([tx(1, L, ME)], listed=[L])
    assert s.hop_distance == 1


def test_listed_address_beyond_the_searched_hops_is_not_reported():
    s = sig([tx(1, ME, B), tx(2, B, C), tx(3, C, L)], listed=[L], hops=2)
    assert s.hop_distance is None and s.searched_hops == 2


def test_cycle_back_to_the_subject_is_found():
    s = sig([tx(1, ME, B), tx(2, B, C), tx(3, C, ME)])
    assert s.cycle_count == 1 and s.shortest_cycle == 3


def test_cycle_longer_than_the_limit_is_ignored():
    chain = [tx(1, ME, B), tx(2, B, C), tx(3, C, X), tx(4, X, Y), tx(5, Y, ME)]
    assert sig(chain).cycle_count == 0


def test_no_cycle_in_a_one_way_flow():
    assert sig([tx(1, ME, B), tx(2, B, C)]).cycle_count == 0


def test_peeling_chain_follows_the_dominant_recipient():
    s = sig([tx(1, ME, B, 90), tx(2, ME, X, 10), tx(3, B, C, 81), tx(4, B, Y, 9)])
    assert s.peel_chain_length == 2


def test_subject_missing_from_the_graph_gives_empty_signals():
    s = sig([tx(1, B, C)], listed=[L])
    assert s.hop_distance is None and s.cycle_count == 0 and s.peel_chain_length == 0
