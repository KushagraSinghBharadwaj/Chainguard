from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.addresses import normalize_address

Address = Annotated[str, AfterValidator(normalize_address)]

HEX_DATA_PATTERN = r"^0x([0-9a-fA-F]{2})*$"
MAX_DATA_LENGTH = 100_002  # "0x" + 100000 hex chars


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AddressLookupRequest(_StrictModel):
    chain_id: int = Field(ge=1)
    addresses: list[Address] = Field(min_length=1, max_length=25)


class AddressAnalyzeRequest(_StrictModel):
    chain_id: int = Field(ge=1)
    address: Address


class TransactionAnalyzeRequest(_StrictModel):
    chain_id: int = Field(ge=1)
    from_address: Address = Field(alias="from")
    to: Address | None
    value_wei: str = Field(pattern=r"^[0-9]{1,78}$")
    data: str = Field(pattern=HEX_DATA_PATTERN, max_length=MAX_DATA_LENGTH)
    typed_data: dict | None = None
