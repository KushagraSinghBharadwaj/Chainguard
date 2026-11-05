"""Builds the real provider clients once and shares them across requests.
Tests replace get_providers with fakes through app.dependency_overrides."""

import threading
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import ApiError
from app.providers.alchemy import build_alchemy_client
from app.providers.cache import ProviderCacheStore
from app.providers.etherscan import EtherscanClient
from app.providers.goplus import GoPlusClient


@dataclass(frozen=True)
class Providers:
    history: Any
    rpc: Any
    explorer: Any
    goplus: Any


_lock = threading.Lock()
_providers: Providers | None = None


def get_providers() -> Providers:
    global _providers
    with _lock:
        if _providers is None:
            key = get_settings().etherscan_api_key
            alchemy = build_alchemy_client()
            if key is None or alchemy is None:
                # Not cached, so fixing the .env and restarting is enough.
                raise ApiError(503, "provider_not_configured", "A data provider is not configured.")
            cache = ProviderCacheStore()
            etherscan = EtherscanClient(key.get_secret_value(), cache=cache)
            _providers = Providers(
                history=etherscan,
                rpc=alchemy,
                explorer=etherscan,
                goplus=GoPlusClient(cache=cache),
            )
        return _providers
