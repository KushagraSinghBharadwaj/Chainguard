"""Wallet feature tests. All data here is SYNTHETIC: fake addresses and invented transactions."""

from datetime import datetime, timedelta, timezone

from app.features.wallet_features import compute_wallet_features
from app.providers.base import TokenTransfer, Transaction
from app.services.wallet_data import HistorySection, WalletHistory

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
ME = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40
D = "0x" + "d" * 40


def tx(i, frm, to, days_ago, value=0, err=False):
    return Transaction(f"0x{i:064x}", i, NOW - timedelta(days=days_ago), frm, to, value, err, None, 21000)


def tok(i, frm, to, contract):
    return TokenTransfer(f"0x{i:064x}", i, NOW, frm, to, contract, "SYN", 18, 1)


def sec(check, items, status="complete"):
    return HistorySection(check, status, tuple(items), 1, "end_of_history", None, "etherscan", NOW)


def hist(txs=(), tokens=(), tx_status="complete", tok_status="complete", first=()):
    first_sec = sec("first_transaction", first) if first else sec("first_transaction", (), "skipped")
    return WalletHistory(
        1, ME, sec("transactions", txs, tx_status), sec("token_transfers", tokens, tok_status), first_sec, NOW
    )


def feats(**kw):
    return compute_wallet_features(hist(**kw), NOW)


def test_empty_history_has_no_invented_numbers():
    f = feats()
    assert f.tx_count == 0 and f.tx_per_day is None and f.window_days is None
    assert f.failed_sent_ratio is None and f.counterparty_diversity is None
    assert f.age_days is None and f.recent_tx_30d is None


def test_fan_in_fan_out_and_diversity():
    f = feats(txs=[tx(1, ME, B, 1), tx(2, ME, C, 2), tx(3, ME, B, 3), tx(4, D, ME, 4)])
    assert (f.sent_count, f.received_count) == (3, 1)
    assert f.fan_out == 2 and f.fan_in == 1 and f.unique_counterparties == 3
    assert f.counterparty_diversity == 3 / 4


def test_failed_ratio_counts_only_transactions_the_wallet_sent():
    f = feats(txs=[tx(1, ME, B, 1), tx(2, ME, B, 2), tx(3, ME, B, 3, err=True), tx(4, ME, B, 4), tx(5, D, ME, 5, err=True)])
    assert f.failed_sent_count == 1 and f.failed_sent_ratio == 1 / 4


def test_volume_excludes_failed_transactions():
    f = feats(txs=[tx(1, ME, B, 1, value=10), tx(2, ME, B, 2, value=99, err=True), tx(3, D, ME, 3, value=7)])
    assert f.eth_sent_wei == 10 and f.eth_received_wei == 7


def test_recent_count_is_exact_for_a_complete_history():
    f = feats(txs=[tx(1, ME, B, 5), tx(2, ME, B, 100)])
    assert f.recent_tx_30d == 1


def test_recent_count_is_unknown_when_a_partial_window_does_not_reach_30_days():
    f = feats(txs=[tx(1, ME, B, 2), tx(2, ME, B, 10)], tx_status="partial")
    assert f.recent_tx_30d is None and f.tx_history_complete is False


def test_recent_count_is_exact_when_a_partial_window_reaches_past_30_days():
    f = feats(txs=[tx(1, ME, B, 2), tx(2, ME, B, 100)], tx_status="partial")
    assert f.recent_tx_30d == 1


def test_age_comes_from_the_first_transaction_only():
    f = feats(txs=[tx(1, ME, B, 1)], first=[tx(9, ME, B, 400)])
    assert f.age_days == 400


def test_age_is_none_when_the_first_transaction_is_not_known():
    assert feats(txs=[tx(1, ME, B, 1)]).age_days is None


def test_token_features_and_incomplete_flag():
    f = feats(
        tokens=[tok(1, ME, B, "0x" + "1" * 40), tok(2, D, ME, "0x" + "1" * 40), tok(3, ME, C, "0x" + "2" * 40)],
        tok_status="partial",
    )
    assert f.token_transfer_count == 3 and f.unique_tokens == 2 and f.token_counterparties == 3
    assert f.token_history_complete is False


def test_contract_creation_is_counted_and_not_a_counterparty():
    f = feats(txs=[tx(1, ME, None, 1)])
    assert f.contract_creations == 1 and f.unique_counterparties == 0 and f.counterparty_diversity is None


def test_frequency_uses_the_fetched_window_and_needs_two_transactions():
    assert feats(txs=[tx(1, ME, B, 0)]).tx_per_day is None
    f = feats(txs=[tx(1, ME, B, 10), tx(2, ME, B, 5), tx(3, ME, B, 0)])
    assert f.window_days == 10 and abs(f.tx_per_day - 0.3) < 1e-9


def test_complete_flags_follow_the_section_status():
    f = feats(txs=[tx(1, ME, B, 1)])
    assert f.tx_history_complete is True and f.token_history_complete is True


def test_creation_of_this_address_by_another_account_is_counted_separately():
    f = feats(txs=[tx(1, B, None, 1), tx(2, D, ME, 2)])
    assert f.created_this_address == 1 and f.received_count == 1 and f.contract_creations == 0
    assert f.sent_count + f.received_count + f.created_this_address == f.tx_count
