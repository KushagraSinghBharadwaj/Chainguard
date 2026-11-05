from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ChainGuard API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Secrets: SecretStr never prints its value in logs or repr output.
    database_url: SecretStr | None = None
    etherscan_api_key: SecretStr | None = None
    alchemy_api_key: SecretStr | None = None
    rpc_url_ethereum: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()