import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx

from app.core.addresses import normalize_address
from app.core.config import get_settings
from app.providers.base import (
    ContractSource,
    ProviderResult,
    ResultStatus,
    TokenTransfer,
    Transaction,
)

logger = logging.getLogger("chainguard.provider.etherscan")

# httpx logs full request URLs at INFO, and our URLs carry the API key.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

BASE_URL = "https://api.etherscan.io/v2/api"
PROVIDER = "etherscan"


class Throttle:
    """Spaces calls at least 1/per_second apart. Thread-safe."""

    def __init__(
        self,
        per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / per_second
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self._interval
        delay = start - now
        if delay > 0:
            self._sleep(delay)


@dataclass(frozen=True)
class _Outcome:
    status: ResultStatus
    data: Any = None
    detail: str | None = None
    retry: bool = False


def _classify_body(body: Any) -> _Outcome:
    if not isinstance(body, dict):
        return _Outcome("unavailable", detail="unexpected_shape")
    status = str(body.get("status", ""))
    message = str(body.get("message", ""))
    result = body.get("result")
    if status == "1":
        return _Outcome("ok", data=result)
    if status == "0" and message.lower().startswith("no transactions found") and result == []:
        return _Outcome("ok", data=[], detail="no_transactions")
    text = (result if isinstance(result, str) else message).lower()
    if "rate limit" in text or "community free api limit" in text:
        return _Outcome("rate_limited", detail="rate_limited", retry=True)
    if "too many invalid api key" in text:
        return _Outcome("unavailable", detail="too_many_invalid_api_key_attempts")
    if "invalid api key" in text:
        return _Outcome("unavailable", detail="invalid_api_key")
    if "free api access is not supported" in text:
        return _Outcome("unavailable", detail="chain_not_on_plan")
    if "chainid" in text:
        return _Outcome("unavailable", detail="unsupported_chain")
    return _Outcome("unavailable", detail="provider_error")


def _parse_transaction(row: dict[str, Any]) -> Transaction:
    to = row["to"]
    data = row.get("input", "0x")
    return Transaction(
        hash=row["hash"],
        block_number=int(row["blockNumber"]),
        timestamp=datetime.fromtimestamp(int(row["timeStamp"]), tz=timezone.utc),
        from_address=normalize_address(row["from"]),
        to_address=normalize_address(to) if to else None,
        value_wei=int(row["value"]),
        is_error=row["isError"] == "1",
        input_selector=data[:10] if len(data) >= 10 else None,
        gas_used=int(row["gasUsed"]),
    )


def _parse_token_transfer(row: dict[str, Any]) -> TokenTransfer:
    return TokenTransfer(
        hash=row["hash"],
        block_number=int(row["blockNumber"]),
        timestamp=datetime.fromtimestamp(int(row["timeStamp"]), tz=timezone.utc),
        from_address=normalize_address(row["from"]),
        to_address=normalize_address(row["to"]),
        contract_address=normalize_address(row["contractAddress"]),
        token_symbol=row["tokenSymbol"],
        token_decimals=int(row["tokenDecimal"]),
        value_raw=int(row["value"]),
    )


def _to_result(out: _Outcome, parse: Callable[[dict[str, Any]], Any]) -> ProviderResult:
    if out.status != "ok":
        return ProviderResult(out.status, PROVIDER, None, out.detail)
    if not isinstance(out.data, list):
        return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")
    try:
        return ProviderResult("ok", PROVIDER, [parse(r) for r in out.data], out.detail)
    except (KeyError, TypeError, ValueError):
        return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")


class EtherscanClient:
    """Etherscan API V2 adapter. Failures are typed results, never empty data."""

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        requests_per_second: float = 3.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        timeout_seconds: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        throttle: Throttle | None = None,
    ) -> None:
        self._key = api_key
        self._http = http or httpx.Client()
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._timeout = timeout_seconds
        self._sleep = sleep
        self._throttle = throttle or Throttle(requests_per_second)

    def _attempt(self, query: dict[str, Any]) -> _Outcome:
        try:
            resp = self._http.get(BASE_URL, params=query, timeout=self._timeout)
        except httpx.HTTPError as exc:
            # Class name only: exception text can contain the request URL (and key).
            return _Outcome("unavailable", detail=type(exc).__name__, retry=True)
        if resp.status_code == 429:
            return _Outcome("rate_limited", detail="http_429", retry=True)
        if resp.status_code >= 500:
            return _Outcome("unavailable", detail=f"http_{resp.status_code}", retry=True)
        if resp.status_code != 200:
            return _Outcome("unavailable", detail=f"http_{resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            return _Outcome("unavailable", detail="invalid_json")
        return _classify_body(body)

    def _call(self, chain_id: int, module: str, action: str, **params: Any) -> _Outcome:
        query = {"chainid": chain_id, "module": module, "action": action, "apikey": self._key, **params}
        outcome = _Outcome("unavailable", detail="no_attempt")
        for attempt in range(1, self._max_attempts + 1):
            self._throttle.wait()
            outcome = self._attempt(query)
            if not outcome.retry or attempt == self._max_attempts:
                break
            delay = self._backoff * attempt
            if outcome.status == "rate_limited":
                delay = max(delay, 1.0)
            self._sleep(delay)
        if outcome.status != "ok":
            logger.warning(
                "provider call failed",
                extra={"extra_fields": {"provider": PROVIDER, "status": outcome.status, "detail": outcome.detail}},
            )
        return _Outcome(outcome.status, outcome.data, outcome.detail, False)

    def _list_call(
        self,
        chain_id: int,
        action: str,
        address: str,
        page: int,
        page_size: int,
        newest_first: bool,
        parse: Callable[[dict[str, Any]], Any],
    ) -> ProviderResult:
        if page < 1 or not 1 <= page_size <= 1000:
            raise ValueError("invalid pagination")
        out = self._call(
            chain_id,
            "account",
            action,
            address=normalize_address(address),
            startblock=0,
            endblock=99999999,
            page=page,
            offset=page_size,
            sort="desc" if newest_first else "asc",
        )
        return _to_result(out, parse)

    def get_transactions(
        self, chain_id: int, address: str, *, page: int = 1, page_size: int = 100, newest_first: bool = True
    ) -> ProviderResult[list[Transaction]]:
        return self._list_call(chain_id, "txlist", address, page, page_size, newest_first, _parse_transaction)

    def get_token_transfers(
        self, chain_id: int, address: str, *, page: int = 1, page_size: int = 100, newest_first: bool = True
    ) -> ProviderResult[list[TokenTransfer]]:
        return self._list_call(chain_id, "tokentx", address, page, page_size, newest_first, _parse_token_transfer)

    def get_contract_source(self, chain_id: int, address: str) -> ProviderResult[ContractSource]:
        out = self._call(chain_id, "contract", "getsourcecode", address=normalize_address(address))
        if out.status != "ok":
            return ProviderResult(out.status, PROVIDER, None, out.detail)
        try:
            rows = out.data
            if not isinstance(rows, list) or len(rows) != 1:
                raise ValueError("unexpected result")
            row = rows[0]
            verified = bool(row["SourceCode"].strip())
            impl = row.get("Implementation")
            data = ContractSource(
                verified=verified,
                contract_name=(row.get("ContractName") or None) if verified else None,
                compiler_version=(row.get("CompilerVersion") or None) if verified else None,
                abi_json=row["ABI"] if verified else None,
                is_proxy=row.get("Proxy") == "1",
                implementation=normalize_address(impl) if impl else None,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")
        return ProviderResult("ok", PROVIDER, data, None)


@lru_cache
def build_etherscan_client() -> EtherscanClient | None:
    key = get_settings().etherscan_api_key
    if key is None:
        return None
    return EtherscanClient(key.get_secret_value())
