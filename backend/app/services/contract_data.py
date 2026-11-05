"""Contract data service.

Gathers what the providers say about one contract address, as separate sections that each
carry their own status, source and timestamp. Nothing is merged into a verdict here.

Proxy detection checks several patterns because no single one is reliable:
  - EIP-1967 implementation slot
  - EIP-1967 beacon slot (the beacon is asked for its implementation)
  - legacy zos slot (USDC uses this one; its EIP-1967 slot reads as zero)
  - EIP-1167 minimal proxy bytecode (only the canonical 45-byte clone)
  - the explorer's own proxy flag
"no_known_pattern_found" means these patterns were checked and not found. It does NOT
mean the contract is not a proxy. If any check could not run, the conclusion is "unknown".

An address with no code, or with EIP-7702 delegated code (0xef0100 + 20 bytes), is an
account rather than a contract. Contract-only checks are skipped for it.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, Literal, Protocol, TypeVar

from eth_utils import keccak

from app.core.addresses import normalize_address
from app.providers.base import (
    ContractInfoProvider,
    ContractSource,
    ProviderResult,
    RpcProvider,
)

T = TypeVar("T")

SectionStatus = Literal["ok", "not_found", "rate_limited", "unavailable", "skipped"]
CheckStatus = Literal["completed", "rate_limited", "unavailable", "skipped"]
CodeKind = Literal["no_code", "contract", "eip7702_delegation"]
ProxyPattern = Literal[
    "eip1967_implementation", "eip1967_beacon", "zos_legacy", "eip1167_minimal", "etherscan_reported"
]
Conclusion = Literal["proxy_detected", "no_known_pattern_found", "unknown"]


def _slot_from_label(label: str, minus_one: bool) -> str:
    n = int.from_bytes(keccak(text=label), "big") - (1 if minus_one else 0)
    return "0x" + n.to_bytes(32, "big").hex()


SLOT_EIP1967_IMPLEMENTATION = _slot_from_label("eip1967.proxy.implementation", True)
SLOT_EIP1967_BEACON = _slot_from_label("eip1967.proxy.beacon", True)
SLOT_ZOS_IMPLEMENTATION = _slot_from_label("org.zeppelinos.proxy.implementation", False)
BEACON_IMPLEMENTATION_SELECTOR = "0x5c60da1b"  # implementation()

_HEX = re.compile(r"0x([0-9a-fA-F]{2})*")
_WORD = re.compile(r"0x[0-9a-fA-F]{64}")
_CLONE = re.compile(r"363d3d373d3d3d363d73([0-9a-f]{40})5af43d82803e903d91602b57fd5bf3")


class TokenSecurityProvider(Protocol):
    def token_security(self, chain_id: int, address: str) -> ProviderResult[Any]: ...


@dataclass(frozen=True)
class Section(Generic[T]):
    check: str
    status: SectionStatus
    data: T | None
    detail: str | None  # short machine label, never a provider message
    source: str | None
    fetched_at: datetime | None


@dataclass(frozen=True)
class BytecodeInfo:
    kind: CodeKind
    size_bytes: int
    code_hash: str | None  # keccak256 of the runtime code
    delegation_target: str | None  # EIP-7702
    clone_target: str | None  # EIP-1167


@dataclass(frozen=True)
class ProxyFinding:
    pattern: ProxyPattern
    implementation: str | None
    beacon: str | None
    evidence_source: str
    detail: str | None


@dataclass(frozen=True)
class ProxyCheck:
    pattern: ProxyPattern
    status: CheckStatus
    found: bool
    detail: str | None


@dataclass(frozen=True)
class ProxyAnalysis:
    conclusion: Conclusion
    findings: tuple[ProxyFinding, ...]
    checks: tuple[ProxyCheck, ...]
    implementation: str | None  # first implementation found, in the order the patterns are listed
    implementations_disagree: bool


@dataclass(frozen=True)
class ContractData:
    chain_id: int
    address: str
    bytecode: Section[BytecodeInfo]
    source: Section[ContractSource]
    proxy: Section[ProxyAnalysis]
    implementation_source: Section[ContractSource]
    token: Section[Any]
    generated_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _skipped(check: str, detail: str) -> Section:
    return Section(check, "skipped", None, detail, None, None)


def _section(check: str, res: ProviderResult) -> Section:
    data = res.data if res.status == "ok" else None
    return Section(check, res.status, data, res.detail, res.provider, res.fetched_at)


def _bytecode_section(res: ProviderResult[str]) -> Section[BytecodeInfo]:
    if res.status != "ok":
        return _section("bytecode", res)
    code = res.data
    if not isinstance(code, str) or not _HEX.fullmatch(code):
        return Section("bytecode", "unavailable", None, "unexpected_shape", res.provider, res.fetched_at)
    body = code[2:].lower()
    size = len(body) // 2
    delegation = None
    clone = None
    if size == 0:
        kind: CodeKind = "no_code"
    elif size == 23 and body.startswith("ef0100"):
        kind = "eip7702_delegation"
        delegation = normalize_address("0x" + body[6:])
    else:
        kind = "contract"
        match = _CLONE.fullmatch(body)
        if match:
            clone = normalize_address("0x" + match.group(1))
    code_hash = "0x" + keccak(bytes.fromhex(body)).hex() if size else None
    info = BytecodeInfo(kind, size, code_hash, delegation, clone)
    return Section("bytecode", "ok", info, None, res.provider, res.fetched_at)


def _address_from_word(value: Any) -> tuple[str | None, str | None]:
    """Returns (address or None, problem or None). A zero word is (None, None)."""
    if not isinstance(value, str) or not _WORD.fullmatch(value):
        return None, "unexpected_shape"
    body = value[2:].lower()
    if int(body, 16) == 0:
        return None, None
    if body[:24] != "0" * 24:
        return None, "not_an_address"
    return normalize_address("0x" + body[24:]), None


def _check_slot(
    rpc: RpcProvider, chain_id: int, addr: str, pattern: ProxyPattern, slot: str
) -> tuple[ProxyCheck, str | None]:
    res = rpc.get_storage_at(chain_id, addr, slot)
    if res.status != "ok":
        status: CheckStatus = "rate_limited" if res.status == "rate_limited" else "unavailable"
        return ProxyCheck(pattern, status, False, res.detail or res.status), None
    target, problem = _address_from_word(res.data)
    if problem:
        return ProxyCheck(pattern, "unavailable", False, problem), None
    return ProxyCheck(pattern, "completed", target is not None, None), target


def _resolve_beacon(rpc: RpcProvider, chain_id: int, beacon: str) -> tuple[str | None, str | None]:
    res = rpc.eth_call(chain_id, beacon, BEACON_IMPLEMENTATION_SELECTOR)
    if res.status != "ok" or res.data is None:
        return None, "beacon_call_" + (res.detail or res.status)
    if res.data.reverted:
        return None, "beacon_call_reverted"
    target, problem = _address_from_word(res.data.return_data)
    if target is None:
        return None, "beacon_" + (problem or "zero_address")
    return target, None


def _analyze_proxy(
    rpc: RpcProvider,
    chain_id: int,
    addr: str,
    bytecode: Section[BytecodeInfo],
    source: Section[ContractSource],
) -> Section[ProxyAnalysis]:
    checks: list[ProxyCheck] = []
    findings: list[ProxyFinding] = []

    chk, impl = _check_slot(rpc, chain_id, addr, "eip1967_implementation", SLOT_EIP1967_IMPLEMENTATION)
    checks.append(chk)
    if impl:
        findings.append(ProxyFinding("eip1967_implementation", impl, None, "storage_slot", None))

    chk, beacon = _check_slot(rpc, chain_id, addr, "eip1967_beacon", SLOT_EIP1967_BEACON)
    checks.append(chk)
    if beacon:
        target, detail = _resolve_beacon(rpc, chain_id, beacon)
        findings.append(ProxyFinding("eip1967_beacon", target, beacon, "storage_slot", detail))

    chk, zos = _check_slot(rpc, chain_id, addr, "zos_legacy", SLOT_ZOS_IMPLEMENTATION)
    checks.append(chk)
    if zos:
        findings.append(ProxyFinding("zos_legacy", zos, None, "storage_slot", None))

    if bytecode.status == "ok" and bytecode.data is not None:
        clone = bytecode.data.clone_target
        checks.append(ProxyCheck("eip1167_minimal", "completed", clone is not None, None))
        if clone:
            findings.append(ProxyFinding("eip1167_minimal", clone, None, "bytecode", None))
    else:
        checks.append(ProxyCheck("eip1167_minimal", "skipped", False, "bytecode_unavailable"))

    if source.status == "ok" and source.data is not None:
        flagged = bool(source.data.is_proxy)
        checks.append(ProxyCheck("etherscan_reported", "completed", flagged, None))
        if flagged:
            findings.append(
                ProxyFinding("etherscan_reported", source.data.implementation, None, "explorer", None)
            )
    else:
        status: CheckStatus = "rate_limited" if source.status == "rate_limited" else "unavailable"
        checks.append(ProxyCheck("etherscan_reported", status, False, source.detail or source.status))

    implementations = [f.implementation for f in findings if f.implementation]
    if findings:
        conclusion: Conclusion = "proxy_detected"
    elif all(c.status == "completed" for c in checks):
        conclusion = "no_known_pattern_found"
    else:
        conclusion = "unknown"
    analysis = ProxyAnalysis(
        conclusion=conclusion,
        findings=tuple(findings),
        checks=tuple(checks),
        implementation=implementations[0] if implementations else None,
        implementations_disagree=len(set(implementations)) > 1,
    )
    nothing_ran = not findings and not any(c.status == "completed" for c in checks)
    section_status: SectionStatus = "unavailable" if nothing_ran else "ok"
    detail = "all_checks_failed" if nothing_ran else None
    return Section("proxy_detection", section_status, analysis, detail, "alchemy,etherscan", _now())


def get_contract_data(
    rpc: RpcProvider,
    explorer: ContractInfoProvider,
    token_intel: TokenSecurityProvider,
    chain_id: int,
    address: str,
) -> ContractData:
    addr = normalize_address(address)
    bytecode = _bytecode_section(rpc.get_code(chain_id, addr))
    info = bytecode.data if bytecode.status == "ok" else None
    if info is not None and info.kind != "contract":
        why = info.kind
        return ContractData(
            chain_id, addr, bytecode,
            _skipped("verified_source", why), _skipped("proxy_detection", why),
            _skipped("implementation_source", why), _skipped("token_security", why),
            _now(),
        )
    source = _section("verified_source", explorer.get_contract_source(chain_id, addr))
    proxy = _analyze_proxy(rpc, chain_id, addr, bytecode, source)
    impl = proxy.data.implementation if proxy.data is not None else None
    if impl is None:
        impl_source = _skipped("implementation_source", "no_implementation_found")
    else:
        impl_source = _section("implementation_source", explorer.get_contract_source(chain_id, impl))
    token = _section("token_security", token_intel.token_security(chain_id, addr))
    return ContractData(chain_id, addr, bytecode, source, proxy, impl_source, token, _now())
