"""End to end: when the stored model metrics are not clearly better than chance,
the final wallet report must contain no score. All data here is SYNTHETIC."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from app.engines.wallet import analyze_wallet
from app.providers.base import ProviderResult, Transaction
from app.services.intel_lookup import IntelLookup, IntelSourceInfo
from app.services.model_inference import score_wallet as real_score_wallet
from app.services.training_model import FEATURES, WINDOW_TX

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
SUBJECT = "0x" + "a" * 40
OTHER = "0x" + "d" * 40
SOURCES = (
    IntelSourceInfo("ofac_sdn", "synthetic-1", NOW),
    IntelSourceInfo("scamsniffer", "synthetic-1", NOW),
)
CUT = 123
NAME = "hgb"


def tx(i, to=OTHER):
    return Transaction(f"0x{i:064x}", i, NOW - timedelta(days=400 - i % 300), SUBJECT, to, 0, False, None, 21000)


class FakeHistory:
    def __init__(self, txs=()):
        self.txs = list(txs)

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        if not newest_first:
            return ProviderResult("ok", "etherscan", self.txs[-1:])
        return ProviderResult("ok", "etherscan", self.txs[(page - 1) * page_size : page * page_size])

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return ProviderResult("ok", "etherscan", [])


class FakeRpc:
    def get_code(self, chain_id, address):
        return ProviderResult("ok", "alchemy", "0x")


class Unused:
    def __getattr__(self, name):
        raise AssertionError(f"{name} should not be called for a plain account")


class FakeGoPlus:
    def address_security(self, chain_id, address):
        return ProviderResult(
            "ok", "goplus",
            SimpleNamespace(flags={"phishing_activities": False}, malicious_contracts_created=0),
        )

    def token_security(self, chain_id, address):
        raise AssertionError("token_security should not be called for a plain account")


def run():
    def intel(chain_id, addresses):
        return IntelLookup({}, SOURCES)

    return analyze_wallet(
        1,
        SUBJECT,
        history_provider=FakeHistory([tx(i) for i in range(1, 31)]),
        rpc=FakeRpc(),
        explorer=Unused(),
        goplus=FakeGoPlus(),
        intel_lookup=intel,
        now=NOW,
    )


def write_model(tmp_path, pr_auc, prevalence=0.2):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(80, len(FEATURES)))
    y = np.array([0, 1] * 40)
    model = HistGradientBoostingClassifier(max_iter=10).fit(X, y)  # tolerates NaN features
    mp = tmp_path / "m.joblib"
    jp = tmp_path / "m.json"
    joblib.dump(
        {
            "model": model,
            "model_name": NAME,
            "features": list(FEATURES),
            "window_transactions": WINDOW_TX,
            "sklearn_version": sklearn.__version__,
            "cut_block": CUT,
            "created_at": "2026-01-01",
            "medians": [0.0] * len(FEATURES),
        },
        mp,
    )
    jp.write_text(
        json.dumps({"split": {"cut_block": CUT, "test_prevalence": prevalence}, "models": {NAME: {"pr_auc": pr_auc}}}),
        encoding="ascii",
    )
    return mp, jp


def use_model(monkeypatch, mp, jp):
    monkeypatch.setattr("app.engines.wallet.score_wallet", lambda h, n: real_score_wallet(h, n, mp, jp))


def ids(report):
    return {e["id"] for e in report["evidence"]}


def test_not_reliable_model_leaves_no_score_in_the_final_report(tmp_path, monkeypatch):
    monkeypatch.setattr("app.engines.wallet.score_wallet", lambda h, n: ({"status": "not_trained", "version": None}, []))
    baseline = run()

    mp, jp = write_model(tmp_path, pr_auc=0.3)  # margin 0.1 < 0.15
    use_model(monkeypatch, mp, jp)
    r = run()

    assert r["model"]["status"] == "not_reliable"
    assert "ml.wallet_score" not in ids(r)
    assert not any("score" in key for key in r["model"])
    blob = json.dumps(r, default=str)
    assert "wallet_score" not in blob
    assert "explanation" not in blob
    assert r["risk_level"] == baseline["risk_level"]


def test_control_reliable_model_does_produce_a_score(tmp_path, monkeypatch):
    mp, jp = write_model(tmp_path, pr_auc=0.5)  # margin 0.3 >= 0.15
    use_model(monkeypatch, mp, jp)
    r = run()
    assert r["model"]["status"] == "available", r["model"]
    assert "ml.wallet_score" in ids(r)