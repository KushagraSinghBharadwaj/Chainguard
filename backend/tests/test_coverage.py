from datetime import datetime, timezone

import pytest

from app.services.contract_data import Section
from app.services.coverage import (
    CoverageItem,
    from_section,
    overall_status,
    required_checks_completed,
    translate_status,
)
from app.services.wallet_data import HistorySection

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ok", "completed"),
        ("complete", "completed"),
        ("not_found", "completed"),
        ("partial", "partial"),
        ("rate_limited", "unavailable"),
        ("unavailable", "unavailable"),
        ("skipped", "skipped"),
    ],
)
def test_status_translation(raw, expected):
    assert translate_status(raw, None)[0] == expected


def test_unknown_status_fails_closed():
    assert translate_status("surprise", None) == ("unavailable", "unknown_status")


def test_rate_limited_keeps_a_label_and_partial_always_has_detail():
    assert translate_status("rate_limited", None)[1] == "rate_limited"
    assert translate_status("partial", None)[1] == "incomplete"
    assert translate_status("not_found", None)[1] == "not_found"


def test_wallet_item_cap_is_partial_with_reason():
    s = HistorySection("transactions", "partial", (), 5, "item_cap", None, "etherscan", NOW)
    item = from_section(s, required=True)
    assert item.status == "partial" and item.detail == "item_cap" and item.required


def test_wallet_provider_failure_after_pages_keeps_both_parts():
    s = HistorySection("transactions", "partial", (), 2, "provider_failure", "unavailable_after_2_pages", "etherscan", NOW)
    assert from_section(s).detail == "provider_failure:unavailable_after_2_pages"


def test_contract_not_found_is_completed():
    s = Section("source", "not_found", None, None, "etherscan", NOW)
    item = from_section(s)
    assert item.status == "completed" and item.detail == "not_found"


def test_skipped_section_keeps_no_source():
    s = Section("source", "skipped", None, "no_code", None, None)
    assert from_section(s).status == "skipped"


def test_partial_required_blocks_low():
    items = [CoverageItem("a", "completed", "x", None, True), CoverageItem("b", "partial", "x", "item_cap", True)]
    assert required_checks_completed(items) is False


def test_optional_unavailable_does_not_block_but_is_not_complete():
    items = [CoverageItem("a", "completed", "x", None, True), CoverageItem("b", "unavailable", "x", "unavailable", False)]
    assert required_checks_completed(items) is True
    assert overall_status(items) == "partial"


def test_overall_complete_and_empty():
    ok = [CoverageItem("a", "completed", "x", None, True), CoverageItem("b", "skipped", None, "no_code", False)]
    assert overall_status(ok) == "complete"
    assert overall_status([]) == "partial"


def test_to_api_hides_required_flag():
    d = CoverageItem("a", "completed", "x", None, True).to_api()
    assert set(d) == {"check", "status", "source", "detail"}
