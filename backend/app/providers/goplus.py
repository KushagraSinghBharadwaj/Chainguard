import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx

from app.core.addresses import normalize_address
from app.providers.base import ProviderResult, ResultStatus
from app.providers.cache import ProviderCacheStore, build_cache_key
from app.providers.etherscan import Throttle

logger = logging.getLogger("chainguard.provider.goplus")

for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

PROVIDER = "goplus"
BASE_URL = "https://api.gopluslabs.io/api/v1"
SUPPORTED_CHAINS = frozenset({1})
_CODE_DETAILS = {2022: "unsupported_chain"}
# Rate limiting is detected by message text: a real GoPlus rate-limit response has not been observed.
_RATE_HINTS = ("too many", "rate limit", "too fast", "frequen")

# 0/1 string fields of /address_security. Anything else stays in `raw` only.
ADDRESS_FLAG_FIELDS = (
    "blacklist_doubt", "blackmail_activities", "contract_address", "cybercrime",
    "darkweb_transactions", "fake_kyc", "fake_standard_interface", "fake_token",
    "financial_crime", "gas_abuse", "honeypot_related_address", "malicious_mining_activities",
    "mixer", "money_laundering", "phishing_activities", "reinit", "sanctioned",
    "stealing_attack",
)


def _flag(value: Any) -> bool | None:
    """GoPlus encodes booleans as the strings '1' and '0'. Anything else is unknown."""
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _number(value: Any, cast: Callable[[str], Any]) -> Any:
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class GoPlusToken:
    address: str
    name: str | None
    symbol: str | None
    is_open_source: bool | None
    is_proxy: bool | None
    is_honeypot: bool | None
    cannot_buy: bool | None
    buy_tax: float | None  # fraction as reported by GoPlus
    sell_tax: float | None
    transfer_tax: float | None
    holder_count: int | None
    trust_list: bool | None
    is_in_dex: bool | None
    fields_present: frozenset[str]  # a missing field means "not provided", never False
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class GoPlusAddress:
    address: str
    flags: Mapping[str, bool | None]
    malicious_contracts_created: int | None
    data_sources: tuple[str, ...]
    raw: Mapping[str, Any]

    def positive_flags(self) -> list[str]:
        """Risk flags GoPlus raised. An empty list means 'not flagged by GoPlus', not 'safe'."""
        return sorted(k for k, v in self.flags.items() if v is True and k != "contract_address")


def _parse_token(address: str, entry: Mapping[str, Any]) -> GoPlusToken:
    return GoPlusToken(
        address=address,
        name=entry.get("token_name") or None,
        symbol=entry.get("token_symbol") or None,
        is_open_source=_flag(entry.get("is_open_source")),
        is_proxy=_flag(entry.get("is_proxy")),
        is_honeypot=_flag(entry.get("is_honeypot")),
        cannot_buy=_flag(entry.get("cannot_buy")),
        buy_tax=_number(entry.get("buy_tax"), float),
        sell_tax=_number(entry.get("sell_tax"), float),
        transfer_tax=_number(entry.get("transfer_tax"), float),
        holder_count=_number(entry.get("holder_count"), int),
        trust_list=_flag(entry.get("trust_list")),
        is_in_dex=_flag(entry.get("is_in_dex")),
        fields_present=frozenset(entry.keys()),
        raw=dict(entry),
    )


def _parse_address(address: str, entry: Mapping[str, Any]) -> GoPlusAddress:
    sources = str(entry.get("data_source") or "")
    return GoPlusAddress(
        address=address,
        flags={name: _flag(entry.get(name)) for name in ADDRESS_FLAG_FIELDS if name in entry},
        malicious_contracts_created=_number(entry.get("number_of_malicious_contracts_created"), int),
        data_sources=tuple(s.strip() for s in sources.split(",") if s.strip()),
        raw=dict(entry),
    )


@dataclass(frozen=True)
class _Outcome:
    status: ResultStatus
    data: Mapping[str, Any] | None = None
    detail: str | None = None
    retry: bool = False


def _classify(body: Any) -> _Outcome:
    if not isinstance(body, dict):
        return _Outcome("unavailable", detail="unexpected_shape")
    code = body.get("code")
    if code == 1:
        result = body.get("result")
        if not isinstance(result, dict):
            return _Outcome("unavailable", detail="unexpected_shape")
        return _Outcome("ok", data=result)
    message = str(body.get("message", "")).lower()
    if isinstance(code, int) and code in _CODE_DETAILS:
        return _Outcome("unavailable", detail=_CODE_DETAILS[code])
    if any(hint in message for hint in _RATE_HINTS):
        return _Outcome("rate_limited", detail="rate_limited", retry=True)
    return _Outcome("unavailable", detail=f"goplus_code_{code}" if isinstance(code, int) else "goplus_code_unknown")


class GoPlusClient:
    """GoPlus adapter (keyless). Failures are typed results, never empty data."""

    def __init__(
        self,
        *,
        http: httpx.Client | None = None,
        requests_per_second: float = 1.0,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        timeout_seconds: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        throttle: Throttle | None = None,
        cache: ProviderCacheStore | None = None,
    ) -> None:
        self._cache = cache
        self._http = http or httpx.Client()
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._timeout = timeout_seconds
        self._sleep = sleep
        self._throttle = throttle or Throttle(requests_per_second)

    def _attempt(self, path: str, params: dict[str, str]) -> _Outcome:
        try:
            resp = self._http.get(f"{BASE_URL}/{path}", params=params, timeout=self._timeout)
        except httpx.HTTPError as exc:
            return _Outcome("unavailable", detail=type(exc).__name__, retry=True)
        if resp.status_code == 429:
            return _Outcome("rate_limited", detail="http_429", retry=True)
        if resp.status_code >= 500:
            return _Outcome("unavailable", detail=f"http_{resp.status_code}", retry=True)
        if resp.status_code in (401, 403):
            return _Outcome("unavailable", detail="auth_error")
        if resp.status_code != 200:
            return _Outcome("unavailable", detail=f"http_{resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            return _Outcome("unavailable", detail="invalid_json")
        return _classify(body)

    def _get(self, path: str, params: dict[str, str]) -> _Outcome:
        outcome = _Outcome("unavailable", detail="no_attempt")
        for attempt in range(1, self._max_attempts + 1):
            self._throttle.wait()
            outcome = self._attempt(path, params)
            if not outcome.retry or attempt == self._max_attempts:
                break
            delay = self._backoff * attempt
            if outcome.status == "rate_limited":
                delay = max(delay, 2.0)
            self._sleep(delay)
        if outcome.status != "ok":
            logger.warning(
                "provider call failed",
                extra={"extra_fields": {"provider": PROVIDER, "status": outcome.status, "detail": outcome.detail}},
            )
        return outcome

    def _cached_get(self, op: str, chain_id: int, addr: str, path: str, params: dict[str, str]):
        # Returns (outcome, fetched_at): the provider answer time, original time for a cache hit.
        # Empty results are never cached: they mean "not found" for tokens but "unavailable" for addresses.
        key = None
        if self._cache is not None:
            key = build_cache_key(PROVIDER, chain_id, op, {"address": addr})
            hit = self._cache.get(key)
            if hit is not None and hit.found:
                return _Outcome("ok", data=hit.raw), hit.fetched_at
        out = self._get(path, params)
        fetched = datetime.now(timezone.utc)
        if key is not None and out.status == "ok" and out.data:
            self._cache.put(key, PROVIDER, "ok", out.data, op, fetched)
        return out, fetched

    def token_security(self, chain_id: int, address: str) -> ProviderResult[GoPlusToken]:
        addr = normalize_address(address)
        if chain_id not in SUPPORTED_CHAINS:
            return ProviderResult("unavailable", PROVIDER, None, "unsupported_chain")
        out, cached_at = self._cached_get(
            "goplus_token", chain_id, addr, f"token_security/{chain_id}", {"contract_addresses": addr}
        )
        if out.status != "ok":
            return ProviderResult(out.status, PROVIDER, None, out.detail)
        result = out.data or {}
        if not result:
            # Observed: GoPlus answers HTTP 200 / code 1 with an empty result for unknown tokens.
            return ProviderResult("not_found", PROVIDER, None, "no_data_for_token")
        entry = result.get(addr)
        if not isinstance(entry, dict):
            return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")
        if not entry:
            return ProviderResult("not_found", PROVIDER, None, "no_data_for_token")
        return ProviderResult("ok", PROVIDER, _parse_token(addr, entry), None, cached_at)

    def address_security(self, chain_id: int, address: str) -> ProviderResult[GoPlusAddress]:
        addr = normalize_address(address)
        if chain_id not in SUPPORTED_CHAINS:
            return ProviderResult("unavailable", PROVIDER, None, "unsupported_chain")
        out, cached_at = self._cached_get(
            "goplus_address", chain_id, addr, f"address_security/{addr}", {"chain_id": str(chain_id)}
        )
        if out.status != "ok":
            return ProviderResult(out.status, PROVIDER, None, out.detail)
        if not out.data:
            return ProviderResult("unavailable", PROVIDER, None, "empty_result")
        return ProviderResult("ok", PROVIDER, _parse_address(addr, out.data), None, cached_at)


@lru_cache
def build_goplus_client() -> GoPlusClient:
    return GoPlusClient(cache=ProviderCacheStore())
