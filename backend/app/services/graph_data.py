"""Budgeted neighbor expansion for the transaction graph.

Fetches one page of recent transactions for the highest-value neighbors of the subject, with a
hard cap on provider calls. The result says exactly how much was covered: a graph built from it
is never a complete picture, so "partial" is the normal outcome for busy neighbors.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.providers.base import Transaction

DEFAULT_MAX_CALLS = 8
NEIGHBOR_PAGE_SIZE = 100

GraphStatus = Literal["completed", "partial", "unavailable", "skipped"]


@dataclass(frozen=True)
class GraphData:
    transactions: tuple[Transaction, ...]  # subject's transactions plus whatever neighbors returned
    status: GraphStatus
    detail: str | None  # short machine labels, never provider messages
    calls_made: int
    neighbors_total: int
    neighbors_expanded: int
    searched_hops: int
    source: str
    fetched_at: datetime


def rank_neighbors(subject: str, txs: list[Transaction]) -> list[str]:
    """Neighbors ordered by total value exchanged (successful transfers only), ties by address."""
    me = subject.lower()
    value: dict[str, int] = {}
    for t in txs:
        if t.is_error or t.to_address is None:
            continue
        a, b = t.from_address.lower(), t.to_address.lower()
        if a == b:
            continue
        if a == me:
            value[b] = value.get(b, 0) + t.value_wei
        elif b == me:
            value[a] = value.get(a, 0) + t.value_wei
    return sorted(value, key=lambda n: (-value[n], n))


def collect_neighbor_graph(
    provider: Any,
    chain_id: int,
    subject: str,
    subject_txs: list[Transaction],
    *,
    max_calls: int = DEFAULT_MAX_CALLS,
    page_size: int = NEIGHBOR_PAGE_SIZE,
) -> GraphData:
    subject = subject.lower()
    ranked = rank_neighbors(subject, subject_txs)
    by_hash: dict[str, Transaction] = {t.hash: t for t in subject_txs}
    now = datetime.now(timezone.utc)
    if not ranked:
        return GraphData(tuple(by_hash.values()), "skipped", "no_neighbors", 0, 0, 0, 1, "etherscan", now)

    calls = expanded = failures = 0
    truncated = False
    stopped_rate_limited = False
    source, fetched_at = "etherscan", now
    for neighbor in ranked[:max_calls]:
        res = provider.get_transactions(chain_id, neighbor, page=1, page_size=page_size, newest_first=True)
        calls += 1
        source, fetched_at = res.provider, res.fetched_at
        if res.status != "ok":
            failures += 1
            if res.status == "rate_limited":
                stopped_rate_limited = True
                break
            continue
        batch = list(res.data or [])
        expanded += 1
        if len(batch) >= page_size:
            truncated = True
        for t in batch:
            by_hash.setdefault(t.hash, t)

    reasons = []
    if len(ranked) > expanded + failures and not stopped_rate_limited:
        reasons.append("call_budget")
    if stopped_rate_limited:
        reasons.append("rate_limited")
    if failures:
        reasons.append("provider_failure")
    if truncated:
        reasons.append("neighbor_history_truncated")

    if expanded == 0:
        status: GraphStatus = "unavailable"
    elif reasons:
        status = "partial"
    else:
        status = "completed"
    return GraphData(
        tuple(by_hash.values()), status, ",".join(reasons) or None, calls, len(ranked), expanded, 2 if expanded else 1,
        source, fetched_at,
    )
