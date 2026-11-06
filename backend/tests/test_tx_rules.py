from datetime import datetime, timezone
from types import SimpleNamespace

from app.engines.tx_rules import call_evidence, spender_of

NOW = datetime.now(timezone.utc)
SP = "0x" + "ab" * 20


def _d(sig, *vals):
    return SimpleNamespace(signature=sig, args=tuple(SimpleNamespace(value=v) for v in vals))


def ids(d):
    return {e.id for e in call_evidence(d, NOW)}


def test_unlimited_approve():
    assert ids(_d("approve(address,uint256)", SP, 2**256 - 1)) == {"tx.approval.unlimited"}


def test_limited_approve():
    assert ids(_d("approve(address,uint256)", SP, 1000)) == {"tx.approval.limited"}


def test_set_approval_for_all():
    assert ids(_d("setApprovalForAll(address,bool)", SP, True)) == {"tx.approval.for_all"}
    assert ids(_d("setApprovalForAll(address,bool)", SP, False)) == set()


def test_permit_and_spender():
    d = _d("permit(address,address,uint256,uint256,uint8,bytes32,bytes32)", "0x" + "11" * 20, SP, 2**256 - 1, 0, 27, "0x", "0x")
    assert ids(d) == {"tx.permit"}
    assert spender_of(d) == SP


def test_not_decoded():
    assert ids(SimpleNamespace(signature=None, args=())) == {"tx.call.not_decoded"}
