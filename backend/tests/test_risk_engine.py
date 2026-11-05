import pytest

from app.engines.evidence import Evidence, decide_level, evidence_level
from app.services.coverage import CoverageItem


def ev(sev, verified, id="x"):
    return Evidence(id, "rule", "claim.", sev, 0.5, verified, {}, "src", None)


def cov(status="completed", required=True):
    return CoverageItem("c", status, "s", None, required)


@pytest.mark.parametrize(
    "sev,verified,expected",
    [
        ("info", True, None),
        ("low", False, "MODERATE"),
        ("moderate", True, "MODERATE"),
        ("high", False, "MODERATE"),
        ("high", True, "HIGH"),
        ("critical", False, "HIGH"),
        ("critical", True, "CRITICAL"),
    ],
)
def test_evidence_level(sev, verified, expected):
    assert evidence_level(ev(sev, verified)) == expected


def test_low_needs_every_required_check_completed():
    assert decide_level([], [cov(), cov()]) == "LOW"
    assert decide_level([], [cov(), cov("partial")]) == "INSUFFICIENT_DATA"
    assert decide_level([], [cov(), cov("unavailable")]) == "INSUFFICIENT_DATA"


def test_optional_gap_does_not_block_low():
    assert decide_level([], [cov(), cov("unavailable", required=False)]) == "LOW"


def test_nothing_required_is_never_low():
    assert decide_level([], []) == "INSUFFICIENT_DATA"
    assert decide_level([], [cov(required=False)]) == "INSUFFICIENT_DATA"


def test_info_only_with_complete_checks_is_low():
    assert decide_level([ev("info", True)], [cov()]) == "LOW"


def test_evidence_beats_missing_checks_and_highest_wins():
    assert decide_level([ev("critical", True)], [cov("unavailable")]) == "CRITICAL"
    assert decide_level([ev("moderate", True), ev("high", True)], [cov("unavailable")]) == "HIGH"


def test_confidence_must_be_between_0_and_1():
    with pytest.raises(ValueError):
        Evidence("x", "rule", "c.", "info", 1.5, True, {}, "s")
