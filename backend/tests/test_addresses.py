import pytest

from app.core.addresses import normalize_address

# Public EIP-55 specification test vectors.
VECTORS = [
    "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
    "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
    "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
    "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb",
]


@pytest.mark.parametrize("addr", VECTORS)
def test_valid_checksum_normalizes_to_lowercase(addr):
    assert normalize_address(addr) == addr.lower()


@pytest.mark.parametrize("addr", VECTORS)
def test_all_lower_and_all_upper_bodies_are_accepted(addr):
    assert normalize_address(addr.lower()) == addr.lower()
    assert normalize_address("0x" + addr[2:].upper()) == addr.lower()


@pytest.mark.parametrize("addr", VECTORS)
def test_bad_checksum_is_rejected(addr):
    body = addr[2:]
    i = next(i for i, ch in enumerate(body) if ch.isalpha())
    bad = "0x" + body[:i] + body[i].swapcase() + body[i + 1 :]
    with pytest.raises(ValueError):
        normalize_address(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "0x",
        "0x123",
        "5aaeb6053f3e94c9b9a09f33669435e7ef1beaed",
        "0X5aaeb6053f3e94c9b9a09f33669435e7ef1beaed",
        "0x" + "g" * 40,
        "0x" + "a" * 41,
        "0x" + "a" * 40 + "\n",
        " 0x" + "a" * 40,
    ],
)
def test_malformed_addresses_are_rejected(bad):
    with pytest.raises(ValueError):
        normalize_address(bad)


def test_non_string_is_rejected():
    with pytest.raises(ValueError):
        normalize_address(123)
