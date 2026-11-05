"""Local store for training-data collection (SQLite). Holds collected rows only; never used by the API."""

import sqlite3
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "training.sqlite"  # backend/data/
LABELS = ("positive", "unlabeled")
MAX_ATTEMPTS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    chain_id INTEGER NOT NULL,
    address TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('positive', 'unlabeled')),
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    cutoff_block INTEGER,
    collected_at TEXT,
    raw_json TEXT,
    PRIMARY KEY (chain_id, address)
)
"""


def connect(path: Path | str = DEFAULT_PATH) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def add_addresses(conn: sqlite3.Connection, chain_id: int, addresses, label: str, source: str) -> int:
    """Insert new addresses as pending. Existing rows are left untouched. Returns how many were new."""
    if label not in LABELS:
        raise ValueError("bad label")
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO samples (chain_id, address, label, source) VALUES (?, ?, ?, ?)",
        [(chain_id, a.lower(), label, source) for a in addresses],
    )
    conn.commit()
    return conn.total_changes - before


def claim_pending(conn: sqlite3.Connection, limit: int, unlabeled_share: float = 0.5) -> list[sqlite3.Row]:
    """Claim up to limit pending rows, mixing labels so a stopped run still has both classes.

    About unlabeled_share of the batch is unlabeled. If one label runs short, the other fills the rest.
    Within a label, rows are taken in insertion order.
    """

    def take(unlabeled: bool, n: int) -> list[sqlite3.Row]:
        if n <= 0:
            return []
        op = "=" if unlabeled else "!="
        return conn.execute(
            "SELECT * FROM samples WHERE status = 'pending' AND label " + op + " 'unlabeled' ORDER BY rowid LIMIT ?",
            (n,),
        ).fetchall()

    want_unlabeled = round(limit * unlabeled_share)
    pos = take(False, limit - want_unlabeled)
    unl = take(True, limit - len(pos))
    if len(pos) + len(unl) < limit:
        pos = take(False, limit - len(unl))
    return unl + pos


def mark_done(conn, chain_id: int, address: str, cutoff_block: int | None, collected_at: str, raw_json: str) -> None:
    conn.execute(
        "UPDATE samples SET status='done', attempts=attempts+1, cutoff_block=?, collected_at=?, raw_json=? "
        "WHERE chain_id=? AND address=?",
        (cutoff_block, collected_at, raw_json, chain_id, address.lower()),
    )
    conn.commit()


def mark_failed(conn, chain_id: int, address: str) -> None:
    """Count the attempt; back to pending until MAX_ATTEMPTS, then failed for good."""
    conn.execute(
        "UPDATE samples SET attempts = attempts + 1, "
        "status = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'pending' END "
        "WHERE chain_id=? AND address=?",
        (MAX_ATTEMPTS, chain_id, address.lower()),
    )
    conn.commit()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT label || ':' || status AS k, COUNT(*) AS n FROM samples GROUP BY k").fetchall()
    return {r["k"]: r["n"] for r in rows}
