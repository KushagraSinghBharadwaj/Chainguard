from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, Literal, Protocol, TypeVar

T = TypeVar("T")

ResultStatus = Literal["ok", "not_found", "rate_limited", "unavailable"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    """Typed outcome of a provider call. A failure is never an empty list.

    ok            data holds the provider answer. An empty list means the provider
                  explicitly said there is nothing (for example "No transactions found").
    not_found     the provider says the subject does not exist.
    rate_limited  the provider refused because of rate limits (after limited retries).
    unavailable   network error, provider error, auth/config problem or unexpected shape.
    detail is a short machine label, never a provider message, URL or secret.
    """

    status: ResultStatus
    provider: str
    data: T | None = None
    detail: str | None = None
    fetched_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class Transaction:
    hash: str
    block_number: int
    timestamp: datetime
    from_address: str
    to_address: str | None  # None for contract creation
    value_wei: int
    is_error: bool
    input_selector: str | None  # first 4 bytes of calldata, e.g. 0xa9059cbb
    gas_used: int


@dataclass(frozen=True)
class TokenTransfer:
    hash: str
    block_number: int
    timestamp: datetime
    from_address: str
    to_address: str
    contract_address: str
    token_symbol: str
    token_decimals: int
    value_raw: int


@dataclass(frozen=True)
class ContractSource:
    verified: bool
    contract_name: str | None
    compiler_version: str | None
    abi_json: str | None
    is_proxy: bool
    implementation: str | None


class WalletHistoryProvider(Protocol):
    def get_transactions(
        self, chain_id: int, address: str, *, page: int = 1, page_size: int = 100, newest_first: bool = True
    ) -> ProviderResult[list[Transaction]]: ...

    def get_token_transfers(
        self, chain_id: int, address: str, *, page: int = 1, page_size: int = 100, newest_first: bool = True
    ) -> ProviderResult[list[TokenTransfer]]: ...


class ContractInfoProvider(Protocol):
    def get_contract_source(self, chain_id: int, address: str) -> ProviderResult[ContractSource]: ...


@dataclass(frozen=True)
class CallOutcome:
    """Result of an eth_call. A revert is a real answer, not a provider failure."""

    reverted: bool
    return_data: str | None  # hex return data when not reverted


class RpcProvider(Protocol):
    def get_code(self, chain_id: int, address: str) -> ProviderResult[str]: ...

    def eth_call(
        self, chain_id: int, to: str, data: str, *, from_address: str | None = None
    ) -> ProviderResult[CallOutcome]: ...

    def get_storage_at(self, chain_id: int, address: str, slot: str) -> ProviderResult[str]: ...


@dataclass(frozen=True)
class CallOutcome:
    """Result of an eth_call. A revert is a real answer, not a provider failure."""

    reverted: bool
    return_data: str | None  # hex return data when not reverted


class RpcProvider(Protocol):
    def get_code(self, chain_id: int, address: str) -> ProviderResult[str]: ...

    def eth_call(
        self, chain_id: int, to: str, data: str, *, from_address: str | None = None
    ) -> ProviderResult[CallOutcome]: ...

    def get_storage_at(self, chain_id: int, address: str, slot: str) -> ProviderResult[str]: ...
