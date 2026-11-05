"""Features evidence tests. Data is SYNTHETIC (see test_wallet_engine.py for the fakes)."""

from tests.test_wallet_engine import SOURCES, run, tx, OFAC
from app.services.intel_lookup import IntelLookup, IntelHit
from tests.test_wallet_engine import OTHER


def features(report):
    return next(e for e in report["evidence"] if e["id"] == "wallet.features")


def test_features_evidence_is_present_and_info_only():
    r = run(txs=[tx(1), tx(2)])
    e = features(r)
    assert e["severity"] == "info" and e["data"]["tx_count"] == 2
    assert r["risk_level"] == "LOW"


def test_features_evidence_does_not_hide_a_critical_finding():
    r = run(txs=[tx(1)], lookup=IntelLookup({OTHER: (OFAC,)}, SOURCES))
    assert r["risk_level"] == "HIGH" and features(r)["severity"] == "info"


def test_wei_values_are_strings_for_json_safety():
    d = features(run(txs=[tx(1)]))["data"]
    assert isinstance(d["eth_sent_wei"], str) and isinstance(d["eth_received_wei"], str)


def test_truncated_history_is_flagged_incomplete():
    r = run(txs=[tx(i) for i in range(1000)], fail_after=1)
    e = features(r)
    assert e["data"]["tx_history_complete"] is False and "lower bounds" in e["claim"]


def test_empty_history_has_no_invented_numbers():
    d = features(run())["data"]
    assert d["tx_per_day"] is None and d["failed_sent_ratio"] is None and d["counterparty_diversity"] is None
