import json
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression

from app.engines.evidence import Evidence, decide_level
from app.services import model_inference as mi
from app.services.coverage import CoverageItem
from app.services.training_model import FEATURES, WINDOW_TX, _section
from app.services.wallet_data import WalletHistory

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
COV = [CoverageItem("a", "completed", "s", None, True)]


def _write(tmp_path, pr_auc=0.9, prevalence=0.4, cut=100, metrics_cut=100, version=None):
    rng = np.random.default_rng(0)
    x = rng.normal(size=(40, len(FEATURES)))
    y = np.array([0, 1] * 20)
    est = LogisticRegression().fit(x, y)
    joblib.dump(
        {
            "model": est, "model_name": "logistic_regression", "features": list(FEATURES),
            "window_transactions": WINDOW_TX, "sklearn_version": version or sklearn.__version__,
            "cut_block": cut, "created_at": "t", "medians": [0.0] * len(FEATURES),
        },
        tmp_path / "m.joblib",
    )
    (tmp_path / "metrics.json").write_text(
        json.dumps({"models": {"logistic_regression": {"pr_auc": pr_auc}},
                    "split": {"test_prevalence": prevalence, "cut_block": metrics_cut}})
    )
    mi._load.cache_clear()
    return str(tmp_path / "m.joblib"), str(tmp_path / "metrics.json")


def _empty():
    return WalletHistory(
        chain_id=1, address="0x" + "1" * 40,
        transactions=_section("transactions", "complete", (), NOW),
        token_transfers=_section("token_transfers", "skipped", (), NOW),
        first_transaction=_section("first_transaction", "skipped", (), NOW),
        generated_at=NOW,
    )


def _ev(sev, verified=True):
    return Evidence(id="x", kind="intel", claim="c", severity=sev, confidence=1.0, verified=verified, data={}, source="s")


def test_not_trained(tmp_path):
    mi._load.cache_clear()
    info, ev = mi.score_wallet(_empty(), NOW, tmp_path / "none.joblib", tmp_path / "none.json")
    assert info["status"] == "not_trained" and ev == []


def test_sklearn_mismatch_is_unavailable(tmp_path):
    m, k = _write(tmp_path, version="0.0.1")
    assert mi._load(m, k)[1] == "unavailable"


def test_metrics_from_other_run_is_unavailable(tmp_path):
    m, k = _write(tmp_path, cut=100, metrics_cut=999)
    assert mi._load(m, k)[1] == "unavailable"


def test_weak_metrics_are_not_reliable_and_hidden(tmp_path):
    m, k = _write(tmp_path, pr_auc=0.5, prevalence=0.4)
    info, ev = mi.score_wallet(_empty(), NOW, m, k)
    assert info["status"] == "not_reliable" and ev == []


def test_strong_metrics_are_available(tmp_path):
    m, k = _write(tmp_path, pr_auc=0.9, prevalence=0.4)
    assert mi._load(m, k)[1] == "available"
    info, ev = mi.score_wallet(_empty(), NOW, m, k)
    assert info["status"] == "unavailable" and info["reason"] == "no transactions" and ev == []


def test_model_never_lowers_level():
    assert decide_level([_ev("critical"), mi.ml_evidence(0.1, [], "v", 0.3, NOW)], COV) == "CRITICAL"
    assert decide_level([_ev("critical"), mi.ml_evidence(0.99, [], "v", 0.3, NOW)], COV) == "CRITICAL"


def test_high_score_alone_caps_at_moderate():
    assert decide_level([mi.ml_evidence(0.99, [], "v", 0.3, NOW)], COV) == "MODERATE"
    assert decide_level([mi.ml_evidence(0.2, [], "v", 0.3, NOW)], COV) == "LOW"
