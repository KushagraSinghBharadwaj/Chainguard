import json
import re
from dataclasses import dataclass

from app.core.addresses import normalize_address

_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class ScamSnifferParseResult:
    """Everything the parser saw, so nothing is dropped silently."""

    addresses: tuple[str, ...]  # unique, normalized, lowercase
    rows_seen: int
    non_evm: int  # not a 0x + 40 hex string (or not a string at all)
    invalid: int  # EVM-shaped but failed address validation (e.g. bad checksum)
    duplicates: int
    rejected_samples: tuple[str, ...]  # up to 10, truncated, for diagnostics


def parse_scamsniffer(raw: bytes | str) -> ScamSnifferParseResult:
    """Parse ScamSniffer's blacklist/all.json and return validated EVM addresses."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("address"), list):
        raise ValueError("unexpected ScamSniffer format: missing 'address' list")

    seen: set[str] = set()
    non_evm = invalid = duplicates = 0
    samples: list[str] = []

    def reject(item: object) -> None:
        if len(samples) < 10:
            samples.append(repr(item)[:60])

    rows = data["address"]
    for item in rows:
        if not isinstance(item, str) or not _EVM.match(item.strip()):
            non_evm += 1
            reject(item)
            continue
        try:
            normalized = normalize_address(item.strip())
        except Exception:  # the validator's error type is not part of this module's contract
            invalid += 1
            reject(item)
            continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)

    return ScamSnifferParseResult(
        addresses=tuple(sorted(seen)),
        rows_seen=len(rows),
        non_evm=non_evm,
        invalid=invalid,
        duplicates=duplicates,
        rejected_samples=tuple(samples),
    )
