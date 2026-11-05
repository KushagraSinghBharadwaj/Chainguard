from datetime import datetime, timedelta, timezone

import pytest

from app.providers.base import ProviderResult, TokenTransfer, Transaction
from app.services.wallet_data import get_wallet_history

ADDR = "0x" + "a" * 40
OTHER = "0x" + "b" * 40
TOKEN = "0x" + "c" * 40
EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


def make_tx(block: int) -> Transaction:
    return Transaction(
        hash=f"0x{block:064x}", block_number=block, timestamp=EPOCH + timedelta(minutes=block),
        from_address=ADDR, to_address=OTHER, value_wei=1, is_error=False,
        input_selector=None, gas_used=21000,
    )


def make_transfer(block: int) -> TokenTransfer:
    return TokenTransfer(
        hash=f"0x{block:064x}", block_number=block, timestamp=EPOCH + timedelta(minutes=block),
        from_address=ADDR, to_address=OTHER, contract_address=TOKEN, token_symbol="USDC",
        token_decimals=6, value_raw=1,
    )


class FakeProvider:
    """FIXTURE (synthetic): serves prebuilt lists in pages the way Etherscan does.
    Test-only. Never imported by product code. Real behavior is covered by live tests."""

    def __init__(self, txs=(), transfers=(), fail=None):
        self.txs = list(txs)
        self.transfers = list(transfers)
        self.fail = fail or {}  # (kind, call_number) -> provider status to inject
        self.calls = []

    def _serve(self, kind, items, page, page_size, newest_first, end_block):
        n = sum(1 for c in self.calls if c["kind"] == kind) + 1
        self.calls.append(
            {"kind": kind, "page": page, "page_size": page_size,
             "newest_first": newest_first, "end_block": end_block}
        )
        status = self.fail.get((kind, n))
        if status:
            return ProviderResult(status, "fake", None, "injected")
        rows = [x for x in items if end_block is None or x.block_number <= end_block]
        rows.sort(key=lambda x: x.block_number, reverse=newest_first)
        start = (page - 1) * page_size
        return ProviderResult("ok", "fake", rows[start : start + page_size])

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return self._serve("tx", self.txs, page, page_size, newest_first, end_block)

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return self._serve("transfer", self.transfers, page, page_size, newest_first, end_block)


def tx_calls(fp):
    return [c for c in fp.calls if c["kind"] == "tx"]


def test_small_history_is_complete_and_first_tx_is_derived():
    fp = FakeProvider([make_tx(b) for b in range(1, 251)])
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=1000)
    t = h.transactions
    assert t.status == "complete" and t.complete and t.stop_reason == "end_of_history"
    assert len(t.items) == 250 and t.items[0].block_number == 250 and t.pages_fetched == 3
    f = h.first_transaction
    assert f.status == "complete" and f.items[0].block_number == 1
    assert f.pages_fetched == 0 and f.detail == "derived_from_transactions"
    assert len(tx_calls(fp)) == 3


def test_exact_page_multiple_ends_with_an_empty_page():
    fp = FakeProvider([make_tx(b) for b in range(1, 201)])
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=1000)
    assert h.transactions.status == "complete" and len(h.transactions.items) == 200
    assert h.transactions.pages_fetched == 3


def test_item_cap_is_partial_and_first_tx_is_fetched_separately():
    fp = FakeProvider([make_tx(b) for b in range(1, 501)])
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    t = h.transactions
    assert t.status == "partial" and not t.complete and t.stop_reason == "item_cap"
    assert len(t.items) == 300 and t.items[0].block_number == 500 and t.items[-1].block_number == 201
    f = h.first_transaction
    assert f.status == "complete" and f.items[0].block_number == 1 and f.pages_fetched == 1
    last = tx_calls(fp)[-1]
    assert last["newest_first"] is False and last["page_size"] == 1


def test_pages_are_pinned_to_the_first_page_block():
    fp = FakeProvider([make_tx(b) for b in range(1, 501)])
    get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    assert [c["end_block"] for c in tx_calls(fp)[:3]] == [None, 500, 500]


def test_first_page_failure_is_not_complete_and_skips_first_tx():
    fp = FakeProvider([make_tx(1)], fail={("tx", 1): "rate_limited"})
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    t = h.transactions
    assert t.status == "rate_limited" and t.items == () and t.pages_fetched == 0
    assert t.stop_reason == "provider_failure" and not t.complete
    assert h.first_transaction.status == "skipped"


def test_mid_history_failure_is_partial_with_what_was_fetched():
    fp = FakeProvider([make_tx(b) for b in range(1, 501)], fail={("tx", 2): "unavailable"})
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    t = h.transactions
    assert t.status == "partial" and t.stop_reason == "provider_failure"
    assert len(t.items) == 100 and t.detail == "injected_after_1_pages"
    assert h.first_transaction.status == "complete" and h.first_transaction.items[0].block_number == 1


def test_empty_wallet_is_complete_and_empty():
    fp = FakeProvider([])
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    assert h.transactions.status == "complete" and h.transactions.items == ()
    assert h.first_transaction.status == "complete" and h.first_transaction.items == ()


def test_token_transfers_are_independent_of_transaction_failures():
    fp = FakeProvider([make_tx(1)], [make_transfer(b) for b in range(1, 6)], fail={("tx", 1): "unavailable"})
    h = get_wallet_history(fp, 1, ADDR, page_size=100, max_items=300)
    assert h.transactions.status == "unavailable"
    assert h.token_transfers.status == "complete" and len(h.token_transfers.items) == 5


@pytest.mark.parametrize(
    "page_size,max_items",
    [(0, 100), (1001, 2002), (100, 50), (100, 10_100), (100, 250)],
)
def test_invalid_limits_are_rejected(page_size, max_items):
    with pytest.raises(ValueError):
        get_wallet_history(FakeProvider([]), 1, ADDR, page_size=page_size, max_items=max_items)


def test_invalid_address_makes_no_provider_calls():
    fp = FakeProvider([])
    with pytest.raises(ValueError):
        get_wallet_history(fp, 1, "0x123")
    assert fp.calls == []
