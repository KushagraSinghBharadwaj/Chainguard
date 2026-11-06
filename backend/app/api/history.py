"""History listing and one combined analyze endpoint. Read-only: never signs or sends."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_client
from app.api.providers_dep import Providers, get_providers
from app.api.wallets import (
    _address_type,
    analyze,
    analyze_token_endpoint,
    require_supported_chain,
)
from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.requests import AddressAnalyzeRequest
from app.services import history_store

router = APIRouter(tags=["history"])


@router.get("/history")
def list_history(
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": history_store.list_for_client(db, auth.client_id, limit)}


@router.post("/analyze")
def analyze_any(
    body: AddressAnalyzeRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> dict[str, Any]:
    """Detect whether the address is a wallet or a contract, then run the matching analysis.
    Contracts get the token checks."""
    require_supported_chain(db, body.chain_id)
    kind = _address_type(providers.rpc, body.chain_id, body.address)
    if kind == "unknown":
        raise ApiError(
            503,
            "address_type_unavailable",
            "Could not tell whether this address is a wallet or a contract. Try again.",
        )
    handler = analyze if kind == "eoa" else analyze_token_endpoint
    report = handler(body, auth, db, providers)
    return {**report, "detected_address_type": kind}
