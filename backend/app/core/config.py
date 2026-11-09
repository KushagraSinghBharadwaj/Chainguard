from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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

    # Rate limits for authenticated routes (burst size and sustained rate per minute).
    rate_limit_token_burst: int = Field(default=30, ge=1)
    rate_limit_token_per_minute: int = Field(default=30, ge=1)
    rate_limit_ip_burst: int = Field(default=60, ge=1)
    rate_limit_ip_per_minute: int = Field(default=60, ge=1)
    # Only set true behind a reverse proxy you control; otherwise X-Forwarded-For is spoofable.
    trust_proxy_headers: bool = False

    # Optional local LLM (Ollama). It only rephrases the engine summary and never changes a level.
    llm_enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    llm_timeout_seconds: float = Field(default=20.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()