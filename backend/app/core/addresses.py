import re

from eth_utils import is_checksum_address

_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")


def normalize_address(value: str) -> str:
    """The only place address strings are parsed.

    Accepts 0x + 40 hex chars. Mixed-case input must pass the EIP-55 checksum.
    Returns the lowercase form used for storage.
    """
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        raise ValueError("invalid address format")
    body = value[2:]
    if body != body.lower() and body != body.upper():
        if not is_checksum_address(value):
            raise ValueError("invalid EIP-55 checksum")
    return value.lower()
