"""Wallet ML score (4.9). Adds evidence only. decide_level takes the max, so the model never lowers a level."""

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.engines.evidence import Evidence
from app.features.wallet_features import compute_wallet_features
from app.services.training_model import FEATURES, WINDOW_TX, _section, feature_vector
from app.services.wallet_data import WalletHistory

logger = logging.getLogger("chainguard.model")

ML_DIR = Path(__file__).resolve().parents[2] / "ml_reports"
MODEL_PATH = ML_DIR / "wallet_model.joblib"
METRICS_PATH = ML_DIR / "wallet_model_metrics.json"
MIN_PR_AUC_MARGIN = 0.15
SUSPICIOUS_SCORE = 0.7
TOP_N = 3
SOURCE = "chainguard_wallet_model"


@lru_cache(maxsize=1)
def _load(model_path: str, metrics_path: str):
    """Return (bundle, status, reason, margin). Never raises."""
    mp = Path(model_path)
    if not mp.exists():
        return None, "not_trained", "no model file", None
    try:
        import joblib
        import sklearn

        b = joblib.load(mp)
        if b["sklearn_version"] != sklearn.__version__:
            return None, "unavailable", "sklearn version mismatch", None
        if b["window_transactions"] != WINDOW_TX or any(n not in FEATURES for n in b["features"]):
            return None, "unavailable", "feature set mismatch", None
        m = json.loads(Path(metrics_path).read_text(encoding="ascii"))
        if m["split"]["cut_block"] != b["cut_block"]:
            return None, "unavailable", "metrics file does not match model", None
        margin = m["models"][b["model_name"]]["pr_auc"] - m["split"]["test_prevalence"]
    except Exception as exc:
        return None, "unavailable", type(exc).__name__, None
    status = "available" if margin >= MIN_PR_AUC_MARGIN else "not_reliable"
    return b, status, None, margin


def ml_evidence(score, explanation, version, margin, now) -> Evidence:
    severity = "low" if score >= SUSPICIOUS_SCORE else "info"
    return Evidence(
        id="ml.wallet_score",
        kind="ml",
        claim=(
            f"An experimental model scores this wallet {score:.2f} (0 to 1) for similarity to wallets on scam lists. "
            "This is not a probability of fraud."
        ),
        severity=severity,
        confidence=0.5,
        verified=False,
        data={"score": round(score, 4), "model": version, "pr_auc_margin": round(margin, 3), "explanation": explanation},
        source=SOURCE,
        fetched_at=now,
    )


def score_wallet(history: WalletHistory, now, model_path=MODEL_PATH, metrics_path=METRICS_PATH):
    """Return (model_info for the report, list of evidence). Never raises."""
    bundle, status, reason, margin = _load(str(model_path), str(metrics_path))
    info = {"status": status, "version": None}
    if bundle is None:
        info["reason"] = reason
        return info, []
    info["version"] = f"{bundle['model_name']}@{bundle['created_at']}"
    info["pr_auc_margin"] = round(margin, 3)
    if status != "available":
        info["reason"] = "stored metrics are not clearly better than chance"
        return info, []
    try:
        import numpy as np

        tx = history.transactions
        items = sorted(tx.items, key=lambda t: (t.block_number, t.timestamp), reverse=True)[:WINDOW_TX]
        if not items:
            info.update(status="unavailable", reason="no transactions")
            return info, []
        h = WalletHistory(
            chain_id=history.chain_id,
            address=history.address,
            transactions=_section("transactions", "complete", items, tx.fetched_at),
            token_transfers=_section("token_transfers", "skipped", (), tx.fetched_at),
            first_transaction=_section("first_transaction", "skipped", (), tx.fetched_at),
            generated_at=history.generated_at,
        )
        full = feature_vector(compute_wallet_features(h, max(t.timestamp for t in items)))
        x = [full[FEATURES.index(n)] for n in bundle["features"]]
        arr = np.array([x], dtype=float)
        model = bundle["model"]
        score = float(model.predict_proba(arr)[0, 1])
        meds = bundle["medians"]
        swapped = np.repeat(arr, len(x), axis=0)
        for j in range(len(x)):
            swapped[j, j] = meds[j]
        deltas = score - model.predict_proba(swapped)[:, 1]
        order = sorted(range(len(x)), key=lambda j: -deltas[j])[:TOP_N]
        explanation = [
            {
                "feature": bundle["features"][j],
                "value": None if x[j] != x[j] else x[j],
                "typical": None if meds[j] != meds[j] else meds[j],
                "effect": round(float(deltas[j]), 3),
            }
            for j in order
            if deltas[j] > 0.01
        ]
        return info, [ml_evidence(score, explanation, info["version"], margin, now)]
    except Exception as exc:
        logger.warning("model scoring failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
        info.update(status="unavailable", reason=type(exc).__name__)
        return info, []
