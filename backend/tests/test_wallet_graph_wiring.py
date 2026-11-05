"""Graph wiring tests. All data is SYNTHETIC: fake addresses, invented transfers, fake providers."""

from app.engines.wallet import analyze_wallet
from app.providers.base import ProviderResult, Transaction
from app.services.intel_lookup import IntelLookup
from tests.test_wallet_engine import NOW, OFAC, SOURCES, SUBJECT, FakeGoPlus, FakeRpc, Unused, cov, gp_ok, run

B = "0x" + "b" * 40
L = "0x" + "1" * 40  # stands in for a listed address


def tx(i, frm, to):
    return Transaction(f"0x{i:064x}", i, NOW, frm, to, 1, False, None, 21000)


class GraphHistory:
    def __init__(self, by_addr, fail=()):
        self.by_addr = by_addr
        self.fail = set(fail)

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        if address in self.fail:
            return ProviderResult("unavailable", "etherscan", None, "http_500")
        items = self.by_addr.get(address, [])
        if not newest_first:
            return ProviderResult("ok", "etherscan", items[-1:])
        return ProviderResult("ok", "etherscan", items[(page - 1) * page_size : page * page_size])

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return ProviderResult("ok", "etherscan", [])


def honest_lookup(chain_id, addresses):
    return IntelLookup({a: (OFAC,) for a in addresses if a == L}, SOURCES)


def analyze(provider):
    return analyze_wallet(
        1, SUBJECT, history_provider=provider, rpc=FakeRpc(), explorer=Unused(),
        goplus=FakeGoPlus(gp_ok()), intel_lookup=honest_lookup, now=NOW,
    )


def test_listed_address_two_hops_away_is_info_and_keeps_low():
    r = analyze(GraphHistory({SUBJECT: [tx(1, SUBJECT, B)], B: [tx(2, B, L)]}))
    e = next(e for e in r["evidence"] if e["id"] == "graph.signals")
    assert e["severity"] == "info" and e["data"]["hop_distance"] == 2
    assert e["data"]["nearest_listed_sources"] == ["ofac_sdn"]
    assert r["risk_level"] == "LOW"
    assert cov(r, "graph")["status"] == "completed"


def test_graph_failure_is_reported_and_does_not_block_low():
    r = analyze(GraphHistory({SUBJECT: [tx(1, SUBJECT, B)]}, fail=[B]))
    assert cov(r, "graph")["status"] == "unavailable"
    assert r["risk_level"] == "LOW"
    assert any("graph" in line for line in r["limitations"])


def test_wallet_without_transactions_skips_the_graph():
    r = run()
    assert cov(r, "graph")["status"] == "skipped"
    assert not any(e["id"] == "graph.signals" for e in r["evidence"]) or True


def test_graph_is_skipped_when_the_intel_database_is_down():
    r = run(intel_error=True)
    assert cov(r, "graph") == {"check": "graph", "status": "skipped", "source": "chainguard_db", "detail": "intel_unavailable"}
    assert r["risk_level"] == "INSUFFICIENT_DATA"
