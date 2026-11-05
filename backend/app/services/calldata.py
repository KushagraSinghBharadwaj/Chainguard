"""Calldata decoder.

Decodes transaction calldata from two sources, and says which one it used:
  - "verified_abi": the ABI of a verified contract (for a proxy, the implementation ABI).
  - "standard_table": a built-in table of well-known token, approval and multicall functions.

Cautions this module encodes:
  - Function names inside a verified ABI are chosen by whoever deployed the contract. A
    function called "transfer" in a contract ABI is only a label, not proof it behaves like
    ERC-20 transfer. Only a signature that matches the standard table gets a standard family.
  - approve(address,uint256) and transferFrom(address,address,uint256) are shared by ERC-20
    and ERC-721. Calldata alone cannot say whether the number is an amount or a token id.
  - A selector with no match is reported as unknown. It is never guessed.
  - multicall(bytes[]) hides inner calls, so they are decoded recursively (depth and count
    are capped).
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from eth_abi import decode as abi_decode
from eth_utils import keccak

from app.core.addresses import normalize_address
from app.services.contract_data import ContractData

DecodeStatus = Literal["decoded", "unknown_selector", "decode_failed", "no_calldata", "malformed"]
Source = Literal["verified_abi", "standard_table"]

MAX_CALLDATA_HEX = 200_002  # "0x" + 100,000 bytes
MAX_ABI_CHARS = 2_000_000
MAX_DEPTH = 3
MAX_INNER_CALLS = 50

_HEX = re.compile(r"0x([0-9a-fA-F]{2})*")
_SHARED_721 = "selector_shared_by_erc20_and_erc721"


def selector_of(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


@dataclass(frozen=True)
class StandardFunction:
    signature: str
    family: str
    note: str | None = None


_STANDARD = (
    StandardFunction("transfer(address,uint256)", "erc20"),
    StandardFunction("approve(address,uint256)", "erc20_or_erc721", _SHARED_721),
    StandardFunction("transferFrom(address,address,uint256)", "erc20_or_erc721", _SHARED_721),
    StandardFunction("increaseAllowance(address,uint256)", "erc20_extension"),
    StandardFunction("decreaseAllowance(address,uint256)", "erc20_extension"),
    StandardFunction("permit(address,address,uint256,uint256,uint8,bytes32,bytes32)", "eip2612_permit"),
    StandardFunction("safeTransferFrom(address,address,uint256)", "erc721"),
    StandardFunction("safeTransferFrom(address,address,uint256,bytes)", "erc721"),
    StandardFunction("setApprovalForAll(address,bool)", "erc721_or_erc1155"),
    StandardFunction("safeTransferFrom(address,address,uint256,uint256,bytes)", "erc1155"),
    StandardFunction("safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)", "erc1155"),
    StandardFunction("deposit()", "weth"),
    StandardFunction("withdraw(uint256)", "weth"),
    StandardFunction("approve(address,address,uint160,uint48)", "permit2"),
    StandardFunction("multicall(bytes[])", "multicall"),
)

STANDARD_BY_SELECTOR: dict[str, StandardFunction] = {}
for _fn in _STANDARD:
    _sel = selector_of(_fn.signature)
    if _sel in STANDARD_BY_SELECTOR:
        raise RuntimeError("duplicate selector in the standard table: " + _fn.signature)
    STANDARD_BY_SELECTOR[_sel] = _fn


@dataclass(frozen=True)
class DecodedArg:
    name: str | None
    type: str
    value: Any


@dataclass(frozen=True)
class DecodedCall:
    status: DecodeStatus
    selector: str | None = None
    signature: str | None = None
    function_name: str | None = None
    args: tuple[DecodedArg, ...] = ()
    source: Source | None = None
    abi_label: str | None = None
    family: str | None = None
    inner_calls: tuple["DecodedCall", ...] = ()
    detail: str | None = None  # short machine label for failures
    notes: tuple[str, ...] = ()  # machine labels for cautions


@dataclass(frozen=True)
class _AbiFunction:
    signature: str
    name: str
    types: tuple[str, ...]
    names: tuple[str | None, ...]


def _canonical_type(item: dict[str, Any]) -> str:
    t = item["type"]
    if t.startswith("tuple"):
        inner = ",".join(_canonical_type(c) for c in item["components"])
        return "(" + inner + ")" + t[len("tuple"):]
    return t


def _parse_abi(abi_json: Any) -> dict[str, list[_AbiFunction]] | None:
    if not isinstance(abi_json, str) or len(abi_json) > MAX_ABI_CHARS:
        return None
    try:
        entries = json.loads(abi_json)
        if not isinstance(entries, list):
            return None
        table: dict[str, list[_AbiFunction]] = {}
        for e in entries:
            if not isinstance(e, dict) or e.get("type") != "function":
                continue
            inputs = e.get("inputs", [])
            types = tuple(_canonical_type(i) for i in inputs)
            names = tuple((i.get("name") or None) for i in inputs)
            signature = f"{e['name']}({','.join(types)})"
            table.setdefault(selector_of(signature), []).append(
                _AbiFunction(signature, e["name"], types, names)
            )
        return table
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def _split_top_level(inner: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current or parts:
        parts.append("".join(current))
    return parts


def _normalize(abi_type: str, value: Any) -> Any:
    if abi_type.endswith("]"):
        inner = abi_type[: abi_type.rindex("[")]
        return [_normalize(inner, v) for v in value]
    if abi_type.startswith("("):
        parts = _split_top_level(abi_type[1:-1])
        return [_normalize(t, v) for t, v in zip(parts, value, strict=True)]
    if abi_type == "address":
        return normalize_address(value)
    if abi_type.startswith("bytes"):
        return "0x" + bytes(value).hex()
    return value


def _decode(data: Any, parsed: list[tuple[str, dict[str, list[_AbiFunction]]]], depth: int) -> DecodedCall:
    if not isinstance(data, str) or len(data) > MAX_CALLDATA_HEX or not _HEX.fullmatch(data):
        return DecodedCall("malformed", detail="invalid_hex")
    raw = bytes.fromhex(data[2:])
    if len(raw) == 0:
        return DecodedCall("no_calldata")
    if len(raw) < 4:
        return DecodedCall("malformed", detail="shorter_than_selector")
    selector = "0x" + raw[:4].hex()
    payload = raw[4:]
    notes: list[str] = []

    hit: tuple[str, _AbiFunction] | None = None
    for label, table in parsed:
        funcs = table.get(selector)
        if funcs:
            if hit is None:
                hit = (label, funcs[0])
            if len(funcs) > 1:
                notes.append(f"abi_functions_share_selector:{label}")
    standard = STANDARD_BY_SELECTOR.get(selector)

    family: str | None = None
    abi_label: str | None = None
    if hit is not None:
        abi_label, fn = hit
        source: Source = "verified_abi"
        signature, name, types, names = fn.signature, fn.name, fn.types, fn.names
        if standard is not None and standard.signature != signature:
            notes.append(f"selector_also_matches_standard:{standard.signature}")
        elif standard is not None:
            family = standard.family
            if standard.note:
                notes.append(standard.note)
    elif standard is not None:
        source = "standard_table"
        signature = standard.signature
        name = signature.split("(")[0]
        types = tuple(_split_top_level(signature[signature.index("(") + 1 : -1]))
        names = (None,) * len(types)
        family = standard.family
        if standard.note:
            notes.append(standard.note)
    else:
        return DecodedCall(
            "unknown_selector",
            selector=selector,
            detail="selector_not_in_known_abis_or_standard_table",
            notes=tuple(notes),
        )

    def failed(detail: str) -> DecodedCall:
        return DecodedCall(
            "decode_failed", selector, signature, name, (), source, abi_label, family, (), detail, tuple(notes)
        )

    try:
        values = abi_decode(list(types), payload) if types else ()
    except Exception as exc:  # untrusted input: any decoder error is a failed decode, class name only
        return failed(type(exc).__name__)
    if not types and payload:
        notes.append("trailing_bytes_ignored")
    try:
        args = tuple(
            DecodedArg(n, t, _normalize(t, v)) for n, t, v in zip(names, types, values, strict=True)
        )
    except (ValueError, TypeError):
        return failed("unexpected_value")

    inner: tuple[DecodedCall, ...] = ()
    if signature == "multicall(bytes[])" and args:
        if depth >= MAX_DEPTH:
            notes.append("nested_depth_limit")
        else:
            calls = args[0].value
            if len(calls) > MAX_INNER_CALLS:
                notes.append("inner_calls_truncated")
                calls = calls[:MAX_INNER_CALLS]
            inner = tuple(_decode(c, parsed, depth + 1) for c in calls)
    return DecodedCall("decoded", selector, signature, name, args, source, abi_label, family, inner, None, tuple(notes))


def decode_calldata(data: str, abis: Sequence[tuple[str, str]] = ()) -> DecodedCall:
    """Decode calldata. abis is an ordered list of (label, abi_json); the first match wins."""
    parsed: list[tuple[str, dict[str, list[_AbiFunction]]]] = []
    abi_notes: list[str] = []
    for label, abi_json in abis:
        table = _parse_abi(abi_json)
        if table is None:
            abi_notes.append(f"abi_unparseable:{label}")
        else:
            parsed.append((label, table))
    result = _decode(data, parsed, 0)
    if abi_notes:
        result = replace(result, notes=tuple(abi_notes) + result.notes)
    return result


def abis_for_contract(contract: ContractData) -> list[tuple[str, str]]:
    """ABIs to try for calls to this contract: implementation first (for proxies), then its own."""
    abis: list[tuple[str, str]] = []
    impl = contract.implementation_source
    if impl.status == "ok" and impl.data is not None and impl.data.verified and impl.data.abi_json:
        abis.append(("implementation", impl.data.abi_json))
    src = contract.source
    if src.status == "ok" and src.data is not None and src.data.verified and src.data.abi_json:
        abis.append(("contract", src.data.abi_json))
    return abis
