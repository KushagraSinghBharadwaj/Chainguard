"""Wallet features: pure functions over an already-fetched history. No network, no thresholds.

Counts come from the fetched window only. When the history is truncated they are lower bounds,
so every feature set carries tx_history_complete / token_history_complete, and a value that
would need the full history is None instead of a guess.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.wallet_data import WalletHistory

RECENT_DAYS = 30


@dataclass(frozen=True)
class WalletFeatures:
    tx_history_complete: bool
    token_history_complete: bool
    age_days: int | None  # None unless the first transaction is known
    tx_count: int  # fetched transactions (lower bound when incomplete)
    sent_count: int
    received_count: int
    contract_creations: int
    window_days: float | None  # time span covered by the fetched transactions
    tx_per_day: float | None  # tx_count over the fetched window; None for fewer than 2 transactions
    recent_tx_30d: int | None  # None when the fetched window does not reach back 30 days
    failed_sent_count: int
    failed_sent_ratio: float | None  # failed / sent, only transactions this wallet sent
    eth_sent_wei: int  # successful transactions only
    eth_received_wei: int  # successful transactions only
    unique_counterparties: int
    fan_out: int  # distinct recipients of transactions this wallet sent
    fan_in: int  # distinct senders of transactions this wallet received
    counterparty_diversity: float | None  # unique counterparties / interactions with others
    token_transfer_count: int
    unique_tokens: int
    token_counterparties: int


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def compute_wallet_features(history: WalletHistory, now: datetime) -> WalletFeatures:
    me = history.address.lower()
    txs = history.transactions.items
    tx_complete = history.transactions.status == "complete"

    sent = received = creations = failed_sent = others = 0
    eth_sent = eth_received = 0
    recipients: set[str] = set()
    senders: set[str] = set()
    for t in txs:
        frm = t.from_address.lower()
        to = t.to_address.lower() if t.to_address else None
        if frm == me:
            sent += 1
            if t.is_error:
                failed_sent += 1
            else:
                eth_sent += t.value_wei
            if to is None:
                creations += 1
            elif to != me:
                recipients.add(to)
                others += 1
        elif to == me:
            received += 1
            if not t.is_error:
                eth_received += t.value_wei
            senders.add(frm)
            others += 1

    stamps = [_utc(t.timestamp) for t in txs]
    window_days: float | None = None
    per_day: float | None = None
    recent: int | None = None
    if stamps:
        oldest, newest = min(stamps), max(stamps)
        cutoff = now - timedelta(days=RECENT_DAYS)
        # Newest-first fetch: the window is exact for the last 30 days if it reaches past the
        # cutoff or the history is complete.
        if tx_complete or oldest <= cutoff:
            recent = sum(1 for s in stamps if s >= cutoff)
        if len(stamps) >= 2:
            window_days = (newest - oldest).total_seconds() / 86400
            per_day = len(stamps) / max(window_days, 1.0)

    counterparties = recipients | senders

    first = history.first_transaction
    age_days: int | None = None
    if first.status == "complete" and first.items:
        age_days = max(0, (now - _utc(first.items[0].timestamp)).days)

    tokens: set[str] = set()
    token_cps: set[str] = set()
    for tr in history.token_transfers.items:
        tokens.add(tr.contract_address.lower())
        frm, to = tr.from_address.lower(), tr.to_address.lower()
        other = to if frm == me else frm
        if other != me:
            token_cps.add(other)

    return WalletFeatures(
        tx_history_complete=tx_complete,
        token_history_complete=history.token_transfers.status == "complete",
        age_days=age_days,
        tx_count=len(txs),
        sent_count=sent,
        received_count=received,
        contract_creations=creations,
        window_days=window_days,
        tx_per_day=per_day,
        recent_tx_30d=recent,
        failed_sent_count=failed_sent,
        failed_sent_ratio=(failed_sent / sent) if sent else None,
        eth_sent_wei=eth_sent,
        eth_received_wei=eth_received,
        unique_counterparties=len(counterparties),
        fan_out=len(recipients),
        fan_in=len(senders),
        counterparty_diversity=(len(counterparties) / others) if others else None,
        token_transfer_count=len(history.token_transfers.items),
        unique_tokens=len(tokens),
        token_counterparties=len(token_cps),
    )
