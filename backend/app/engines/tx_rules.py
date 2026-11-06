"""Transaction rules (Phase 6). Pure functions: decoded calldata in, evidence out. Never signs."""

from datetime import datetime
from typing import Any

from app.engines.evidence import Evidence

UINT_UNLIMITED = 2**255  # anything this large is treated as an unlimited allowance


def _ev(id_: str, claim: str, severity: str, data: dict[str, Any], fetched_at: datetime) -> Evidence:
    return Evidence(
        id=id_, kind="rule", claim=claim, severity=severity, confidence=1.0,
        verified=True, data=data, source="calldata", fetched_at=fetched_at,
    )


def _arg(decoded: Any, i: int) -> Any:
    try:
        return decoded.args[i].value
    except (IndexError, AttributeError):
        return None


def _num(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def spender_of(decoded: Any) -> str | None:
    """The address that gains power over the user's assets, if the call grants any."""
    sig = getattr(decoded, "signature", None)
    if sig in ("approve(address,uint256)", "increaseAllowance(address,uint256)", "setApprovalForAll(address,bool)"):
        v = _arg(decoded, 0)
    elif sig == "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)":
        v = _arg(decoded, 1)
    elif sig == "approve(address,address,uint160,uint48)":
        v = _arg(decoded, 1)
    else:
        return None
    return v if isinstance(v, str) else None


def recipient_of(decoded: Any) -> str | None:
    sig = getattr(decoded, "signature", None)
    if sig == "transfer(address,uint256)":
        v = _arg(decoded, 0)
    elif sig in ("transferFrom(address,address,uint256)", "safeTransferFrom(address,address,uint256)"):
        v = _arg(decoded, 1)
    else:
        return None
    return v if isinstance(v, str) else None


def call_evidence(decoded: Any, fetched_at: datetime) -> list[Evidence]:
    sig = getattr(decoded, "signature", None)
    if sig is None:
        return [_ev("tx.call.not_decoded",
                    "The call could not be decoded, so what it does is unknown. Unknown is not safe.",
                    "low", {}, fetched_at)]
    out: list[Evidence] = []
    if sig in ("approve(address,uint256)", "increaseAllowance(address,uint256)"):
        amt = _num(_arg(decoded, 1))
        if amt is not None and amt >= UINT_UNLIMITED:
            out.append(_ev("tx.approval.unlimited",
                           "This call grants an unlimited token allowance. The spender can move all of this token.",
                           "high", {"spender": spender_of(decoded)}, fetched_at))
        elif amt is not None and amt > 0:
            out.append(_ev("tx.approval.limited", "This call grants a limited token allowance.",
                           "info", {"spender": spender_of(decoded), "amount": str(amt)}, fetched_at))
    elif sig == "setApprovalForAll(address,bool)":
        if _arg(decoded, 1) in (True, "true", "True", 1):
            out.append(_ev("tx.approval.for_all",
                           "This call lets the operator move every NFT in this collection.",
                           "high", {"operator": spender_of(decoded)}, fetched_at))
    elif sig == "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)":
        amt = _num(_arg(decoded, 2))
        out.append(_ev("tx.permit",
                       "This is a signature-based approval (permit). It grants an allowance without a separate approve call.",
                       "high" if amt is not None and amt >= UINT_UNLIMITED else "moderate",
                       {"spender": spender_of(decoded)}, fetched_at))
    elif sig == "approve(address,address,uint160,uint48)":
        out.append(_ev("tx.permit2.approval",
                       "This call grants a Permit2 allowance to a spender.",
                       "moderate", {"spender": spender_of(decoded)}, fetched_at))
    return out


def target_evidence(bytecode: Any, source: Any, fetched_at: datetime) -> list[Evidence]:
    if bytecode.status == "ok" and bytecode.data is not None and bytecode.data.kind != "contract":
        return [_ev("tx.target.not_contract",
                    "The target address has no contract code, so calldata sent to it does nothing useful.",
                    "low", {"kind": bytecode.data.kind}, fetched_at)]
    if source.status == "ok" and source.data is not None and not source.data.verified:
        return [_ev("tx.target.unverified",
                    "The target contract has no verified source, so its code cannot be reviewed.",
                    "moderate", {}, fetched_at)]
    return []
