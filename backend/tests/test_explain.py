import pytest

from app.services.explain import should_explain, validate_explanation

SOURCE = (
    "MODERATE risk. Verified ABI exposes blacklist functions: addBlackList, removeBlackList. "
    "Presence is a fact, not proof of misuse. owner() returns an active owner address."
)
GOOD = (
    "Risk level: MODERATE. The contract code lists blacklist functions, which is a fact and "
    "not proof of misuse. It also has an active owner address."
)


def check(text):
    return validate_explanation(text, level="MODERATE", source_text=SOURCE)


def test_good_text_passes():
    assert check(GOOD) == (True, "ok")


@pytest.mark.parametrize(
    "bad",
    [
        "Risk level: HIGH. The contract lists blacklist functions.",
        "The contract lists blacklist functions. Risk level: MODERATE.",
        "Risk level: MODERATE. This could potentially be used to transfer funds.",
        "Risk level: MODERATE.\n- blacklist functions exist\n- an owner exists",
        "Risk level: MODERATE. The data has 60% confidence.",
        "Risk level: MODERATE. The [alchemy] owner is active.",
        "Risk level: MODERATE. One fact. Two facts. Three facts.",
        "Risk level: MODERATE. This is a low risk contract.",
        "Risk level: MODERATE. The contract is safe.",
        "",
    ],
)
def test_bad_text_is_rejected(bad):
    ok, _ = check(bad)
    assert ok is False


def test_only_elevated_levels_are_explained():
    assert should_explain({"risk_level": "MODERATE"})
    assert should_explain({"risk_level": "HIGH"})
    assert not should_explain({"risk_level": "LOW"})
    assert not should_explain({"risk_level": "INSUFFICIENT_DATA"})