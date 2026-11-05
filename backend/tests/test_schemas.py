import pytest
from pydantic import ValidationError

from app.schemas.requests import (
    AddressAnalyzeRequest,
    AddressLookupRequest,
    TransactionAnalyzeRequest,
)

A = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
B = "0x" + "b" * 40


def _tx(**over):
    base = {"chain_id": 1, "from": A, "to": B, "value_wei": "0", "data": "0x"}
    base.update(over)
    return base


def test_lookup_normalizes_addresses():
    r = AddressLookupRequest(chain_id=1, addresses=[A])
    assert r.addresses == [A.lower()]


@pytest.mark.parametrize("addresses", [[], [B] * 26])
def test_lookup_list_size_limits(addresses):
    with pytest.raises(ValidationError):
        AddressLookupRequest(chain_id=1, addresses=addresses)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        AddressAnalyzeRequest(chain_id=1, address=A, extra="x")


def test_chain_id_must_be_integer_and_positive():
    with pytest.raises(ValidationError):
        AddressAnalyzeRequest(chain_id="1", address=A)
    with pytest.raises(ValidationError):
        AddressAnalyzeRequest(chain_id=0, address=A)


def test_bad_address_is_rejected():
    with pytest.raises(ValidationError):
        AddressAnalyzeRequest(chain_id=1, address="0x123")


def test_transaction_valid_with_null_to_and_calldata():
    r = TransactionAnalyzeRequest(**_tx(to=None, data="0xa9059cbb" + "00" * 64))
    assert r.to is None
    assert r.from_address == A.lower()


@pytest.mark.parametrize(
    "over",
    [
        {"value_wei": "-1"},
        {"value_wei": "1.5"},
        {"value_wei": ""},
        {"data": "0xzz"},
        {"data": "0xabc"},
        {"data": "abcd"},
        {"data": "0x" + "00" * 50_001},
    ],
)
def test_transaction_field_validation(over):
    with pytest.raises(ValidationError):
        TransactionAnalyzeRequest(**_tx(**over))
