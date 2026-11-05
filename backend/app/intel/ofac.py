import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import BinaryIO

from app.core.addresses import normalize_address

ETH_LABEL = "Digital Currency Address - ETH"
_PREFIX = "Digital Currency Address - "
_HEX_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class OfacEntry:
    address: str  # normalized, lowercase
    label: str | None  # sanctioned party name(s) from the SDN list


@dataclass(frozen=True)
class OfacParseResult:
    """Everything the parser saw, so nothing is dropped silently."""

    entries: tuple[OfacEntry, ...]  # unique Ethereum (ETH feature type) addresses
    published: date | None  # first DateOfIssue in the file
    eth_rows_seen: int  # raw ETH address rows before dedupe
    rejected: int  # ETH rows that failed address validation
    other_0x_rows: dict[str, int]  # 0x rows under non-ETH labels (not loaded), by label


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_date(el: ET.Element) -> date | None:
    parts = {_local(c.tag): (c.text or "").strip() for c in el}
    try:
        return date(int(parts["Year"]), int(parts["Month"]), int(parts["Day"]))
    except (KeyError, ValueError):
        return None


def _identity_name(identity: ET.Element) -> str | None:
    aliases = [a for a in identity if _local(a.tag) == "Alias"]
    primary = [a for a in aliases if a.get("Primary") == "true"] or aliases
    for alias in primary:
        for doc_name in alias:
            if _local(doc_name.tag) != "DocumentedName":
                continue
            parts = [(v.text or "").strip() for v in doc_name.iter() if _local(v.tag) == "NamePartValue"]
            parts = [p for p in parts if p]
            if parts:
                return " ".join(parts)
    return None


def parse_sdn_advanced(source: str | Path | BinaryIO) -> OfacParseResult:
    """Stream-parse OFAC's SDN_ADVANCED.XML and return validated Ethereum addresses."""
    type_names: dict[str, str] = {}
    identity_names: dict[str, str | None] = {}
    raw: list[tuple[str, str, str | None]] = []  # (feature type id, address, identity id)
    published: date | None = None
    date_seen = False

    for _, el in ET.iterparse(source):
        tag = _local(el.tag)
        if tag == "FeatureType":
            type_names[el.get("ID", "")] = (el.text or "").strip()
        elif tag == "Identity":
            identity_names[el.get("ID", "")] = _identity_name(el)
            el.clear()
        elif tag == "Feature":
            type_id = el.get("FeatureTypeID", "")
            identity_id: str | None = None
            found: list[str] = []
            for child in el.iter():
                name = _local(child.tag)
                if name == "IdentityReference" and identity_id is None:
                    identity_id = child.get("IdentityID")
                elif name == "VersionDetail":
                    text = (child.text or "").strip()
                    if _HEX_ADDRESS.match(text):
                        found.append(text)
            raw.extend((type_id, a, identity_id) for a in found)
            el.clear()
        elif tag == "DateOfIssue" and not date_seen:
            date_seen = True
            published = _parse_date(el)

    eth_ids = {i for i, n in type_names.items() if n == ETH_LABEL}
    labels_by_address: dict[str, list[str]] = {}
    other: Counter[str] = Counter()
    eth_seen = 0
    rejected = 0
    for type_id, address, identity_id in raw:
        if type_id not in eth_ids:
            other[type_names.get(type_id, f"unknown_type_{type_id}").removeprefix(_PREFIX)] += 1
            continue
        eth_seen += 1
        try:
            normalized = normalize_address(address)
        except Exception:  # the validator's error type is not part of this module's contract
            rejected += 1
            continue
        labels = labels_by_address.setdefault(normalized, [])
        label = identity_names.get(identity_id) if identity_id else None
        if label and label not in labels:
            labels.append(label)

    entries = tuple(
        OfacEntry(address=a, label="; ".join(ls) if ls else None)
        for a, ls in sorted(labels_by_address.items())
    )
    return OfacParseResult(entries, published, eth_seen, rejected, dict(other))
