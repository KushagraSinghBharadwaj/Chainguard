"""Wallet model training and evaluation (4.8). Offline: reads the collection store, writes a metrics file.

Features come from the shared feature module, computed with each row's collected_at as "now".
Token-based features are not used because the store keeps only transactions.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.features.wallet_features import compute_wallet_features
from app.providers.base import Transaction
from app.services import training_store as ts
from app.services.wallet_data import HistorySection, WalletHistory

THRESHOLDS = (0.3, 0.5, 0.7)
RANDOM_STATE = 0
MIN_ROWS = 20
RECENCY_FEATURE = "recent_tx_30d"
WINDOW_TX = 200

FEATURES = (
    "tx_count",
    "sent_count",
    "received_count",
    "contract_creations",
    "created_this_address",
    "window_days",
    "tx_per_day",
    "recent_tx_30d",
    "failed_sent_count",
    "failed_sent_ratio",
    "eth_sent",
    "eth_received",
    "unique_counterparties",
    "fan_out",
    "fan_in",
    "counterparty_diversity",
)

EXCLUDED = {
    "age_days": "needs the first transaction, which the newest-window cut removes",
    "tx_history_complete": "coverage flag, not behavior",
    "token_history_complete": "coverage flag, not behavior",
    "token_transfer_count": "token transfers are not stored",
    "unique_tokens": "token transfers are not stored",
    "token_counterparties": "token transfers are not stored",
}

LIMITS = [
    "Positives come from OFAC and ScamSniffer lists, which carry no listing date, so features include activity after listing.",
    "Non-fraud rows are unlabeled counterparties of collected wallets, not verified clean wallets. Contracts and unknown address kinds are excluded.",
    "Unlabeled wallets were sampled from counterparties of positives, so they are linked to scam activity and are not typical wallets.",
    "The class ratio is a sampling choice, not the real-world rate. PR-AUC and precision depend on it; test prevalence is reported.",
    "The split is by cutoff_block (newest block in each stored history), which is last activity, not listing date.",
    "Every wallet is cut to its newest 200 transactions and features use only that window, so capped and short histories look alike. Recency is measured against each wallet's own last transaction, not collection time. Original partial shares per class are still reported.",
    "gradient_boosting_without_recency drops recent_tx_30d to show how much the score depends on recent activity.",
    "decision_stump is a one-split baseline learned from training data. It is not the production rules engine.",
    "No accuracy claim is valid without these stored metrics.",
]


def _section(check, status, items, fetched_at):
    stop = "end_of_history" if status == "complete" else "not_attempted"
    return HistorySection(check, status, tuple(items), 0, stop, None, "training_store", fetched_at)


def row_to_history(row, window: int = WINDOW_TX) -> WalletHistory:
    """Rebuild a WalletHistory from a stored row, cut to the newest `window` transactions.

    Every wallet is described by the same kind of window, so a capped history cannot be told apart from a short one.
    Token transfers are not stored, and the first transaction is skipped because the cut removes it.
    """
    data = json.loads(row["raw_json"])
    collected = datetime.fromisoformat(row["collected_at"])
    txs = []
    for t in data["transactions"]:
        t = dict(t)
        t["timestamp"] = datetime.fromisoformat(t["timestamp"])
        txs.append(Transaction(**t))
    txs.sort(key=lambda t: (t.block_number, t.timestamp), reverse=True)
    txs = txs[:window]
    return WalletHistory(
        chain_id=row["chain_id"],
        address=row["address"],
        transactions=_section("transactions", "complete", txs, collected),
        token_transfers=_section("token_transfers", "skipped", (), collected),
        first_transaction=_section("first_transaction", "skipped", (), collected),
        generated_at=collected,
    )


def feature_vector(f) -> list[float]:
    values = {
        "age_days": f.age_days,
        "tx_count": f.tx_count,
        "sent_count": f.sent_count,
        "received_count": f.received_count,
        "contract_creations": f.contract_creations,
        "created_this_address": f.created_this_address,
        "window_days": f.window_days,
        "tx_per_day": f.tx_per_day,
        "recent_tx_30d": f.recent_tx_30d,
        "failed_sent_count": f.failed_sent_count,
        "failed_sent_ratio": f.failed_sent_ratio,
        "eth_sent": f.eth_sent_wei / 1e18,
        "eth_received": f.eth_received_wei / 1e18,
        "unique_counterparties": f.unique_counterparties,
        "fan_out": f.fan_out,
        "fan_in": f.fan_in,
        "counterparty_diversity": f.counterparty_diversity,
    }
    return [float("nan") if values[n] is None else float(values[n]) for n in FEATURES]


def load_rows(conn, chain_id: int):
    return conn.execute(
        "SELECT chain_id, address, label, cutoff_block, collected_at, raw_json FROM samples "
        "WHERE chain_id = ? AND status = 'done' ORDER BY rowid",
        (chain_id,),
    ).fetchall()


def build_dataset(rows, window: int = WINDOW_TX):
    """Return (records, count of rows skipped for having no transactions).

    Features are computed as of each wallet's own last transaction, not collection time.
    """
    recs = []
    skipped = 0
    for r in rows:
        if r["cutoff_block"] is None:
            skipped += 1
            continue
        h = row_to_history(r, window)
        items = h.transactions.items
        if not items:
            skipped += 1
            continue
        as_of = max(t.timestamp for t in items)
        f = compute_wallet_features(h, as_of)
        stored = json.loads(r["raw_json"])
        recs.append(
            {
                "address": r["address"],
                "y": 1 if r["label"] == "positive" else 0,
                "block": r["cutoff_block"],
                "partial": stored["status"] != "complete",
                "cut": len(stored["transactions"]) > window,
                "x": feature_vector(f),
            }
        )
    return recs, skipped


def balance(recs) -> dict:
    pos = [r for r in recs if r["y"] == 1]
    unl = [r for r in recs if r["y"] == 0]
    return {
        "positive": len(pos),
        "unlabeled": len(unl),
        "partial_positive": sum(1 for r in pos if r["partial"]),
        "partial_unlabeled": sum(1 for r in unl if r["partial"]),
    }


def time_split(recs, test_fraction: float = 0.3):
    """Older cutoff_block goes to train, newer to test. Each side must contain both classes."""
    if len(recs) < MIN_ROWS:
        raise ValueError(f"need at least {MIN_ROWS} rows with transactions, have {len(recs)}")
    blocks = sorted(r["block"] for r in recs)
    cut_block = blocks[int(len(blocks) * (1 - test_fraction))]
    train = [r for r in recs if r["block"] < cut_block]
    test = [r for r in recs if r["block"] >= cut_block]
    for name, part in (("train", train), ("test", test)):
        pos = sum(r["y"] for r in part)
        if pos == 0 or pos == len(part):
            raise ValueError(f"{name} split has one class only ({pos} positive of {len(part)})")
    return train, test, cut_block


def model_specs():
    import numpy as np
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import FunctionTransformer, StandardScaler
    from sklearn.tree import DecisionTreeClassifier

    def impute():
        return SimpleImputer(strategy="median", add_indicator=True)

    def boosting():
        return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=RANDOM_STATE)

    all_idx = list(range(len(FEATURES)))
    no_recency = [i for i, n in enumerate(FEATURES) if n != RECENCY_FEATURE]
    return {
        "majority_class": (DummyClassifier(strategy="prior"), all_idx),
        "decision_stump": (
            make_pipeline(impute(), DecisionTreeClassifier(max_depth=1, random_state=RANDOM_STATE)),
            all_idx,
        ),
        "logistic_regression": (
            make_pipeline(impute(), FunctionTransformer(np.log1p), StandardScaler(), LogisticRegression(max_iter=2000)),
            all_idx,
        ),
        "gradient_boosting": (boosting(), all_idx),
        "gradient_boosting_without_recency": (boosting(), no_recency),
    }


def evaluate(model, x, y) -> dict:
    from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

    p = model.predict_proba(x)[:, 1]
    out = {
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "at_threshold": {},
    }
    for th in THRESHOLDS:
        pred = (p >= th).astype(int)
        out["at_threshold"][str(th)] = {
            "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "predicted_positive": int(pred.sum()),
        }
    return out


def train_and_report(recs, test_fraction: float = 0.3) -> dict:
    import numpy as np
    import sklearn

    train, test, cut_block = time_split(recs, test_fraction)
    xtr = np.array([r["x"] for r in train], dtype=float)
    ytr = np.array([r["y"] for r in train])
    xte = np.array([r["x"] for r in test], dtype=float)
    yte = np.array([r["y"] for r in test])
    models = {}
    for name, (est, idx) in model_specs().items():
        est.fit(xtr[:, idx], ytr)
        models[name] = evaluate(est, xte[:, idx], yte)
        models[name]["feature_count"] = len(idx)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "random_state": RANDOM_STATE,
        "window_transactions": WINDOW_TX,
        "sklearn_version": sklearn.__version__,
        "split": {
            "method": "time, by cutoff_block (newest block in each stored history)",
            "test_fraction": test_fraction,
            "cut_block": cut_block,
            "train": balance(train),
            "test": balance(test),
            "test_prevalence": float(yte.mean()),
        },
        "features": list(FEATURES),
        "excluded_features": EXCLUDED,
        "thresholds": list(THRESHOLDS),
        "models": models,
        "limits": LIMITS,
    }


def save_model(recs, name: str, path: str, test_fraction: float = 0.3) -> None:
    """Refit one model on the train split only, so it matches the stored test metrics, and save it."""
    import joblib
    import numpy as np
    import sklearn

    train, _test, cut_block = time_split(recs, test_fraction)
    est, idx = model_specs()[name]
    xtr = np.array([r["x"] for r in train], dtype=float)[:, idx]
    ytr = np.array([r["y"] for r in train])
    est.fit(xtr, ytr)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": est,
            "model_name": name,
            "features": [FEATURES[i] for i in idx],
            "window_transactions": WINDOW_TX,
            "sklearn_version": sklearn.__version__,
            "cut_block": cut_block,
            "medians": np.nanmedian(xtr, axis=0).tolist(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        out,
    )


def run(conn, chain_id: int, test_fraction: float = 0.3) -> dict:
    rows = load_rows(conn, chain_id)
    recs, without_tx = build_dataset(rows)
    report = train_and_report(recs, test_fraction)
    report["chain_id"] = chain_id
    report["rows"] = {
        "done": len(rows),
        "used": len(recs),
        "without_transactions": without_tx,
        "overall": balance(recs),
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-id", type=int, default=1)
    ap.add_argument("--test-fraction", type=float, default=0.3)
    ap.add_argument("--out", default="ml_reports/wallet_model_metrics.json")
    ap.add_argument("--save-model", default="", help="model name to save, e.g. gradient_boosting")
    ap.add_argument("--model-out", default="ml_reports/wallet_model.joblib")
    args = ap.parse_args()

    conn = ts.connect(str(ts.DEFAULT_PATH))
    try:
        report = run(conn, args.chain_id, args.test_fraction)
    except ValueError as exc:
        raise SystemExit(f"cannot train: {exc}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii", newline="\n")

    s = report["split"]
    print("rows:", report["rows"])
    print("split at block", s["cut_block"], "| train", s["train"], "| test", s["test"])
    print("test prevalence:", round(s["test_prevalence"], 3), "(PR-AUC of a random scorer)")
    for name, m in report["models"].items():
        at = m["at_threshold"]["0.5"]
        print(f"{name:36s} pr_auc={m['pr_auc']:.3f} roc_auc={m['roc_auc']:.3f} p@0.5={at['precision']:.3f} r@0.5={at['recall']:.3f}")
    print("saved:", out)
    if args.save_model:
        recs, _ = build_dataset(load_rows(conn, args.chain_id))
        save_model(recs, args.save_model, args.model_out, args.test_fraction)
        print("model saved:", args.model_out)


if __name__ == "__main__":
    main()
