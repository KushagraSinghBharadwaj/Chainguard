"""Training-data collector: loads positives from the stored lists, samples unlabeled counterparties,
and fetches wallet history for pending rows. Resumable through app.services.training_store."""

import argparse
import dataclasses
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IntelEntry, IntelSource
from app.services import training_store as ts
from app.services.wallet_data import get_wallet_history

logger = logging.getLogger("chainguard.collect")

OK_STATUSES = ("complete", "partial")


def _plain(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return dict(vars(obj))


def load_positives(session: Session, conn, chain_id: int) -> dict[str, int]:
    rows = session.execute(
        select(IntelEntry.address, IntelSource.name)
        .join(IntelSource, IntelSource.id == IntelEntry.source_id)
        .where(IntelEntry.address.is_not(None))
        .where(or_(IntelEntry.chain_id == chain_id, IntelEntry.chain_id.is_(None)))
        .order_by(IntelSource.name, IntelEntry.address)
    ).all()
    by_source: dict[str, list[str]] = {}
    for address, source in rows:
        by_source.setdefault(source, []).append(address)
    return {s: ts.add_addresses(conn, chain_id, a, "positive", s) for s, a in by_source.items()}


def listed_addresses(session: Session, chain_id: int) -> set[str]:
    rows = session.execute(
        select(IntelEntry.address)
        .where(IntelEntry.address.is_not(None))
        .where(or_(IntelEntry.chain_id == chain_id, IntelEntry.chain_id.is_(None)))
    ).scalars()
    return {a.lower() for a in rows}


def sample_unlabeled(conn, chain_id: int, listed: set[str], n: int, per_source: int = 2) -> int:
    """Pick counterparties seen in collected histories. Listed and already-stored addresses are excluded."""
    known = {r["address"] for r in conn.execute("SELECT address FROM samples WHERE chain_id = ?", (chain_id,))}
    picked: list[str] = []
    seen = set(known)
    rows = conn.execute(
        "SELECT address, raw_json FROM samples WHERE chain_id = ? AND status = 'done' ORDER BY rowid", (chain_id,)
    ).fetchall()
    for row in rows:
        if len(picked) >= n:
            break
        taken = 0
        for t in json.loads(row["raw_json"]).get("transactions", []):
            for a in (t.get("from_address"), t.get("to_address")):
                if not a:
                    continue
                a = a.lower()
                if a == row["address"] or a in seen or a in listed:
                    continue
                seen.add(a)
                picked.append(a)
                taken += 1
                if taken >= per_source or len(picked) >= n:
                    break
            if taken >= per_source or len(picked) >= n:
                break
    return ts.add_addresses(conn, chain_id, picked, "unlabeled", "counterparty_of_collected")


def collect_batch(conn, provider, chain_id: int, limit: int) -> dict[str, int]:
    done = failed = 0
    for row in ts.claim_pending(conn, limit):
        addr = row["address"]
        try:
            h = get_wallet_history(provider, chain_id, addr)
            sec = h.transactions
            status = getattr(sec, "status", None)
            if status not in OK_STATUSES:
                raise RuntimeError("history_" + str(status))
            txs = [_plain(t) for t in sec.items]
            blocks = [t.get("block_number") for t in txs if isinstance(t.get("block_number"), int)]
            payload = json.dumps({"status": status, "transactions": txs}, default=str)
            ts.mark_done(conn, chain_id, addr, max(blocks) if blocks else None, sec.fetched_at.isoformat(), payload)
            done += 1
        except Exception as exc:
            logger.warning("collect failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
            ts.mark_failed(conn, chain_id, addr)
            failed += 1
    return {"done": done, "failed": failed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-id", type=int, default=1)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--load-positives", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="add up to N unlabeled counterparties")
    args = ap.parse_args()

    from app.api.providers_dep import get_providers
    from app.db.session import get_engine

    conn = ts.connect()
    engine = get_engine()
    if engine is None:
        raise SystemExit("DATABASE_URL is not set")
    if args.load_positives or args.sample:
        with Session(engine) as session:
            if args.load_positives:
                print("positives added:", load_positives(session, conn, args.chain_id))
            if args.sample:
                print("unlabeled added:", sample_unlabeled(conn, args.chain_id, listed_addresses(session, args.chain_id), args.sample))
    provider = get_providers().history
    print("batch:", collect_batch(conn, provider, args.chain_id, args.limit), "at", datetime.now(timezone.utc).isoformat())
    print("store:", ts.counts(conn))


if __name__ == "__main__":
    main()
