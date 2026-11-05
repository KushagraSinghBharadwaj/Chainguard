import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from app.core.addresses import normalize_address
from app.core.config import get_settings
from app.providers.base import CallOutcome, ProviderResult, ResultStatus
from app.providers.cache import ProviderCacheStore, build_cache_key
from app.providers.etherscan import Throttle

logger = logging.getLogger("chainguard.provider.alchemy")

for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

PROVIDER = "alchemy"
NETWORKS = {1: "eth-mainnet"}
_HEX = set("0123456789abcdefABCDEF")
_RATE_CODES = {429, -32005}


def _is_hex(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("0x") and all(c in _HEX for c in value[2:])


@dataclass(frozen=True)
class _Outcome:
    status: ResultStatus
    data: Any = None
    detail: str | None = None
    retry: bool = False
    reverted: bool = False


def _classify(body: Any, allow_revert: bool) -> _Outcome:
    if not isinstance(body, dict):
        return _Outcome("unavailable", detail="unexpected_shape")
    error = body.get("error")
    if error is not None:
        if not isinstance(error, dict):
            return _Outcome("unavailable", detail="unexpected_shape")
        code = error.get("code")
        text = str(error.get("message", "")).lower()
        if (isinstance(code, int) and code in _RATE_CODES) or "compute units" in text or "rate limit" in text:
            return _Outcome("rate_limited", detail="rate_limited", retry=True)
        if allow_revert and (code == 3 or "revert" in text):
            return _Outcome("ok", reverted=True)
        return _Outcome("unavailable", detail="provider_error")
    if "result" not in body:
        return _Outcome("unavailable", detail="unexpected_shape")
    return _Outcome("ok", data=body["result"])


def _as_hex(out: _Outcome) -> ProviderResult[str]:
    if out.status != "ok":
        return ProviderResult(out.status, PROVIDER, None, out.detail)
    if not _is_hex(out.data):
        return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")
    return ProviderResult("ok", PROVIDER, out.data, None)


class AlchemyClient:
    """Alchemy JSON-RPC adapter. Failures are typed results, never empty data."""

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        requests_per_second: float = 10.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        timeout_seconds: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        throttle: Throttle | None = None,
        cache: ProviderCacheStore | None = None,
    ) -> None:
        self._cache = cache
        self._key = api_key
        self._http = http or httpx.Client()
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._timeout = timeout_seconds
        self._sleep = sleep
        self._throttle = throttle or Throttle(requests_per_second)

    def _attempt(self, url: str, payload: dict[str, Any], allow_revert: bool) -> _Outcome:
        try:
            resp = self._http.post(url, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            # Class name only: exception text can contain the URL, which holds the key.
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
        return _classify(body, allow_revert)

    def _rpc(self, chain_id: int, method: str, params: list[Any], *, allow_revert: bool = False) -> _Outcome:
        network = NETWORKS.get(chain_id)
        if network is None:
            return _Outcome("unavailable", detail="unsupported_chain")
        url = f"https://{network}.g.alchemy.com/v2/{self._key}"
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        outcome = _Outcome("unavailable", detail="no_attempt")
        for attempt in range(1, self._max_attempts + 1):
            self._throttle.wait()
            outcome = self._attempt(url, payload, allow_revert)
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
        return _Outcome(outcome.status, outcome.data, outcome.detail, False, outcome.reverted)

    def _cached_hex(self, op: str, chain_id: int, params: dict[str, Any], method: str, rpc_params: list[Any]) -> ProviderResult[str]:
        # Only used for state reads that are safe to reuse briefly. eth_call is never cached.
        key = None
        if self._cache is not None:
            key = build_cache_key(PROVIDER, chain_id, op, params)
            hit = self._cache.get(key)
            if hit is not None and hit.found and _is_hex(hit.raw):
                return ProviderResult("ok", PROVIDER, hit.raw, None, hit.fetched_at)
        res = _as_hex(self._rpc(chain_id, method, rpc_params))
        if key is not None and res.status == "ok":
            self._cache.put(key, PROVIDER, "ok", res.data, op, res.fetched_at)
        return res

    def get_code(self, chain_id: int, address: str) -> ProviderResult[str]:
        addr = normalize_address(address)
        return self._cached_hex("code", chain_id, {"address": addr}, "eth_getCode", [addr, "latest"])

    def eth_call(
        self, chain_id: int, to: str, data: str, *, from_address: str | None = None
    ) -> ProviderResult[CallOutcome]:
        if not _is_hex(data):
            raise ValueError("invalid calldata")
        call: dict[str, str] = {"to": normalize_address(to), "data": data}
        if from_address is not None:
            call["from"] = normalize_address(from_address)
        out = self._rpc(chain_id, "eth_call", [call, "latest"], allow_revert=True)
        if out.status != "ok":
            return ProviderResult(out.status, PROVIDER, None, out.detail)
        if out.reverted:
            return ProviderResult("ok", PROVIDER, CallOutcome(True, None), "reverted")
        if not _is_hex(out.data):
            return ProviderResult("unavailable", PROVIDER, None, "unexpected_shape")
        return ProviderResult("ok", PROVIDER, CallOutcome(False, out.data), None)

    def get_storage_at(self, chain_id: int, address: str, slot: str) -> ProviderResult[str]:
        if not _is_hex(slot) or len(slot) > 66:
            raise ValueError("invalid storage slot")
        addr = normalize_address(address)
        return self._cached_hex(
            "storage", chain_id, {"address": addr, "slot": slot}, "eth_getStorageAt", [addr, slot, "latest"]
        )


@lru_cache
def build_alchemy_client() -> AlchemyClient | None:
    key = get_settings().alchemy_api_key
    if key is None:
        return None
    return AlchemyClient(key.get_secret_value(), cache=ProviderCacheStore())
