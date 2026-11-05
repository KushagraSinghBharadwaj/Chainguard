"""Wallet history service.

Pages through a provider's transactions and token transfers with a hard item cap and
reports exactly how much was fetched. A truncated or interrupted history is "partial",
never "complete".

Limits worth knowing:
- Etherscan rejects a window larger than 10,000 results (page * page_size), so
  max_items cannot exceed that.
- Pages are pinned to the newest block seen on page 1 (endblock), so new activity
  arriving mid-fetch cannot shift pages and cause duplicates or gaps.
- Token transfers carry no log index, so they are not de-duplicated.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from app.core.addresses import normalize_address
from app.providers.base import (
    ProviderResult,
    TokenTransfer,
    Transaction,
    WalletHistoryProvider,
)

T = TypeVar("T")

SectionStatus = Literal["complete", "partial", "unavailable", "rate_limited", "skipped"]
StopReason = Literal["end_of_history", "item_cap", "provider_failure", "not_attempted"]

MAX_PAGE_SIZE = 1000
PROVIDER_WINDOW = 10_000
DEFAULT_PAGE_SIZE = 1000
DEFAULT_MAX_ITEMS = 5000


@dataclass(frozen=True)
class HistorySection(Generic[T]):
    check: str
    status: SectionStatus
    items: tuple[T, ...]  # newest first; whatever was actually fetched
    pages_fetched: int
    stop_reason: StopReason
    detail: str | None  # short machine label, never a provider message
    source: str
    fetched_at: datetime

    @property
    def complete(self) -> bool:
        return self.status == "complete"


@dataclass(frozen=True)
class WalletHistory:
    chain_id: int
    address: str
    transactions: HistorySection[Transaction]
    token_transfers: HistorySection[TokenTransfer]
    first_transaction: HistorySection[Transaction]
    generated_at: datetime


def _failed(check: str, res: ProviderResult, items: tuple, pages: int) -> HistorySection:
    label = res.detail or res.status
    if pages == 0:
        status: SectionStatus = "rate_limited" if res.status == "rate_limited" else "unavailable"
        return HistorySection(check, status, (), 0, "provider_failure", label, res.provider, res.fetched_at)
    return HistorySection(
        check, "partial", items, pages, "provider_failure", f"{label}_after_{pages}_pages", res.provider, res.fetched_at
    )


def _collect(
    check: str,
    fetch_page: Callable[[int, int | None], ProviderResult[list[Any]]],
    page_size: int,
    max_items: int,
) -> HistorySection:
    items: list[Any] = []
    pages = 0
    pinned: int | None = None
    while True:
        res = fetch_page(pages + 1, pinned)
        if res.status != "ok":
            return _failed(check, res, tuple(items), pages)
        batch = list(res.data or [])
        pages += 1
        if pinned is None and batch:
            pinned = max(x.block_number for x in batch)
        items.extend(batch)
        if len(batch) < page_size:
            return HistorySection(
                check, "complete", tuple(items), pages, "end_of_history", res.detail, res.provider, res.fetched_at
            )
        if len(items) >= max_items:
            # A full last page at the cap: more history may exist, so this is not complete.
            return HistorySection(
                check, "partial", tuple(items), pages, "item_cap", None, res.provider, res.fetched_at
            )


def _first_transaction(
    provider: WalletHistoryProvider,
    chain_id: int,
    address: str,
    transactions: HistorySection[Transaction],
) -> HistorySection[Transaction]:
    check = "first_transaction"
    if transactions.status == "complete":
        oldest = (min(transactions.items, key=lambda t: (t.block_number, t.timestamp)),) if transactions.items else ()
        return HistorySection(
            check, "complete", oldest, 0, "end_of_history", "derived_from_transactions",
            transactions.source, transactions.fetched_at,
        )
    if transactions.status in ("unavailable", "rate_limited"):
        return HistorySection(
            check, "skipped", (), 0, "not_attempted", "transactions_unavailable",
            transactions.source, transactions.fetched_at,
        )
    res = provider.get_transactions(chain_id, address, page=1, page_size=1, newest_first=False)
    if res.status != "ok":
        return _failed(check, res, (), 0)
    return HistorySection(
        check, "complete", tuple(res.data or []), 1, "end_of_history", res.detail, res.provider, res.fetched_at
    )


def get_wallet_history(
    provider: WalletHistoryProvider,
    chain_id: int,
    address: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> WalletHistory:
    if (
        not 1 <= page_size <= MAX_PAGE_SIZE
        or max_items < page_size
        or max_items > PROVIDER_WINDOW
        or max_items % page_size != 0
    ):
        raise ValueError("invalid page_size/max_items")
    addr = normalize_address(address)

    def tx_page(page: int, end_block: int | None) -> ProviderResult[list[Transaction]]:
        return provider.get_transactions(
            chain_id, addr, page=page, page_size=page_size, newest_first=True, end_block=end_block
        )

    def token_page(page: int, end_block: int | None) -> ProviderResult[list[TokenTransfer]]:
        return provider.get_token_transfers(
            chain_id, addr, page=page, page_size=page_size, newest_first=True, end_block=end_block
        )

    transactions = _collect("transactions", tx_page, page_size, max_items)
    token_transfers = _collect("token_transfers", token_page, page_size, max_items)
    first = _first_transaction(provider, chain_id, addr, transactions)
    return WalletHistory(chain_id, addr, transactions, token_transfers, first, datetime.now(timezone.utc))
