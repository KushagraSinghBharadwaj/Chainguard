"""Tests for 4.8 training. All rows here are SYNTHETIC fixtures, not real wallet data."""

import json
from datetime import datetime, timezone

import pytest

from app.features.wallet_features import compute_wallet_features
from app.services import training_model as tm
from app.services import training_store as ts

CHAIN = 1
COLLECTED = "2026-11-05T12:00:00+00:00"


def _addr(prefix, i):
    return "0x" + prefix + format(i, "x").zfill(39)


def _tx(frm, to, block, failed=False):
    stamp = datetime(2024, 1, 1 + block % 20, tzinfo=timezone.utc)
    return {
        "hash": "0x" + format(block, "x").zfill(64),
        "block_number": block,
        "timestamp": str(stamp),
        "from_address": frm,
        "to_address": to,
        "value_wei": 1000,
        "is_error": failed,
        "input_selector": None,
        "gas_used": 21000,
    }


def _fill(mem, label, me, txs, top_block):
    ts.add_addresses(mem, CHAIN, [me], label, "synthetic")
    ts.mark_done(mem, CHAIN, me, top_block, COLLECTED, json.dumps({"status": "complete", "transactions": txs}))


@pytest.fixture
def mem():
    conn = ts.connect(":memory:")
    for i in range(40):
        me = _addr("a", i)
        top = 1000 + 2 * i
        txs = [_tx(me, _addr("c", i * 10 + k), top - k, failed=k < 2) for k in range(4)]
        txs.append(_tx(_addr("d", i), me, top - 5))
        _fill(conn, "positive", me, txs, top)

        me = _addr("b", i)
        top = 1001 + 2 * i
        peer = _addr("e", i)
        txs = [_tx(me, peer, top), _tx(me, peer, top - 1), _tx(peer, me, top - 2)]
        _fill(conn, "unlabeled", me, txs, top)
    return conn


def test_row_to_history_rebuilds_features(mem):
    row = tm.load_rows(mem, CHAIN)[0]
    assert row["label"] == "positive"
    h = tm.row_to_history(row)
    f = compute_wallet_features(h, datetime.fromisoformat(COLLECTED))
    assert (f.sent_count, f.received_count, f.failed_sent_count, f.fan_out, f.fan_in) == (4, 1, 2, 4, 1)
    assert h.first_transaction.status == "skipped" and f.age_days is None


def test_rows_without_transactions_are_excluded(mem):
    me = _addr("f", 1)
    ts.add_addresses(mem, CHAIN, [me], "unlabeled", "synthetic")
    ts.mark_done(mem, CHAIN, me, None, COLLECTED, json.dumps({"status": "complete", "transactions": []}))
    recs, skipped = tm.build_dataset(tm.load_rows(mem, CHAIN))
    assert skipped == 1 and len(recs) == 80


def test_time_split_puts_newer_blocks_in_test(mem):
    recs, _ = tm.build_dataset(tm.load_rows(mem, CHAIN))
    train, test, cut = tm.time_split(recs)
    assert max(r["block"] for r in train) < cut <= min(r["block"] for r in test)
    assert {r["y"] for r in train} == {0, 1} and {r["y"] for r in test} == {0, 1}


def test_split_refuses_a_single_class():
    recs = [{"y": 1, "block": i, "partial": False, "x": []} for i in range(30)]
    with pytest.raises(ValueError):
        tm.time_split(recs)


def test_training_report_on_synthetic_data(mem):
    pytest.importorskip("sklearn")
    recs, _ = tm.build_dataset(tm.load_rows(mem, CHAIN))
    report = tm.train_and_report(recs)
    json.dumps(report)
    assert set(report["models"]) == {
        "majority_class",
        "decision_stump",
        "logistic_regression",
        "gradient_boosting",
        "gradient_boosting_without_recency",
    }
    assert "0.5" in report["models"]["gradient_boosting"]["at_threshold"]
    assert report["models"]["gradient_boosting"]["pr_auc"] > report["split"]["test_prevalence"] + 0.2
    assert report["limits"] and report["excluded_features"]


def test_window_keeps_only_the_newest_transactions(mem):
    me = _addr("f", 2)
    txs = [_tx(me, _addr("c", 900 + k), 5000 - k) for k in range(30)]
    _fill(mem, "unlabeled", me, txs, 5000)
    row = [r for r in tm.load_rows(mem, CHAIN) if r["address"] == me][0]
    h = tm.row_to_history(row, window=10)
    blocks = [t.block_number for t in h.transactions.items]
    assert len(blocks) == 10 and min(blocks) == 4991 and h.transactions.status == "complete"
