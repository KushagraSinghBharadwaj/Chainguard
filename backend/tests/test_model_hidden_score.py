"""A model whose stored metrics are not clearly better than chance must never expose a score."""

import json

import joblib
import numpy as np
import pytest
import sklearn
from sklearn.linear_model import LogisticRegression

from app.services import model_inference as mi
from app.services.training_model import FEATURES, WINDOW_TX

CUT = 123
NAME = "logreg"


def _write(tmp_path, pr_auc, prevalence=0.2, *, sk=None, window=WINDOW_TX, metrics_cut=CUT):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, len(FEATURES)))
    y = np.array([0, 1] * 30)
    model = LogisticRegression(max_iter=200).fit(X, y)
    bundle = {
        "model": model,
        "model_name": NAME,
        "features": list(FEATURES),
        "window_transactions": window,
        "sklearn_version": sk or sklearn.__version__,
        "cut_block": CUT,
        "created_at": "2026-01-01",
        "medians": [0.0] * len(FEATURES),
    }
    mp = tmp_path / "m.joblib"
    jp = tmp_path / "m.json"
    joblib.dump(bundle, mp)
    jp.write_text(
        json.dumps(
            {
                "split": {"cut_block": metrics_cut, "test_prevalence": prevalence},
                "models": {NAME: {"pr_auc": pr_auc}},
            }
        ),
        encoding="ascii",
    )
    return mp, jp


def test_margin_below_threshold_is_not_reliable(tmp_path):
    mp, jp = _write(tmp_path, pr_auc=0.3)  # margin 0.1 < 0.15
    _, status, _, margin = mi._load(str(mp), str(jp))
    assert status == "not_reliable"
    assert margin < mi.MIN_PR_AUC_MARGIN


def test_not_reliable_model_exposes_no_score(tmp_path):
    mp, jp = _write(tmp_path, pr_auc=0.3)
    # object() raises on any attribute access, so this also proves history is never read.
    info, evidence = mi.score_wallet(object(), None, mp, jp)
    assert info["status"] == "not_reliable"
    assert evidence == []
    assert not any("score" in key for key in info)
    assert "wallet_score" not in json.dumps(info)


def test_clearly_better_than_chance_is_available(tmp_path):
    mp, jp = _write(tmp_path, pr_auc=0.5)  # margin 0.3 >= 0.15
    _, status, _, margin = mi._load(str(mp), str(jp))
    assert status == "available"
    assert margin >= mi.MIN_PR_AUC_MARGIN


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sk": "0.0.0"},
        {"window": WINDOW_TX + 1},
        {"metrics_cut": CUT + 1},
    ],
    ids=["sklearn_mismatch", "window_mismatch", "metrics_mismatch"],
)
def test_inconsistent_artifacts_expose_no_score(tmp_path, kwargs):
    mp, jp = _write(tmp_path, pr_auc=0.5, **kwargs)
    info, evidence = mi.score_wallet(object(), None, mp, jp)
    assert info["status"] == "unavailable"
    assert evidence == []


def test_missing_model_exposes_no_score(tmp_path):
    info, evidence = mi.score_wallet(
        object(), None, tmp_path / "nope.joblib", tmp_path / "nope.json"
    )
    assert info["status"] == "not_trained"
    assert evidence == []


def test_corrupt_model_exposes_no_score(tmp_path):
    mp, jp = _write(tmp_path, pr_auc=0.5)
    mp.write_bytes(b"not a model")
    info, evidence = mi.score_wallet(object(), None, mp, jp)
    assert info["status"] == "unavailable"
    assert evidence == []


def test_shipped_model_follows_the_rule():
    if not mi.MODEL_PATH.exists() or not mi.METRICS_PATH.exists():
        pytest.skip("shipped model files not present")
    _, status, _, margin = mi._load(str(mi.MODEL_PATH), str(mi.METRICS_PATH))
    assert status in {"available", "not_reliable", "unavailable", "not_trained"}
    if status in {"available", "not_reliable"}:
        assert (status == "available") == (margin >= mi.MIN_PR_AUC_MARGIN)
    if status != "available":
        info, evidence = mi.score_wallet(object(), None)
        assert evidence == []
        assert not any("score" in key for key in info)