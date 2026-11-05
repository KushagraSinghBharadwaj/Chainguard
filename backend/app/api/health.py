from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import DatabaseStatus, check_database

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime
    database: DatabaseStatus


class ConfigStatusResponse(BaseModel):
    """Reports only whether a value is SET. It does not test connectivity."""

    environment: str
    database_configured: bool
    etherscan_configured: bool
    ethereum_rpc_configured: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(
        status="ok",
        service=s.app_name,
        version=s.app_version,
        timestamp=datetime.now(timezone.utc),
        database=check_database(),
    )


@router.get("/config/status", response_model=ConfigStatusResponse)
def config_status() -> ConfigStatusResponse:
    s = get_settings()
    return ConfigStatusResponse(
        environment=s.app_env,
        database_configured=s.database_url is not None,
        etherscan_configured=s.etherscan_api_key is not None,
        ethereum_rpc_configured=s.rpc_url_ethereum is not None,
    )