"""Wallet analysis and light address lookup."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_client
from app.api.providers_dep import Providers, get_providers
from app.core.errors import ApiError
from app.db.session import get_db
from app.engines.report import ENGINE_VERSION
from app.engines.token import TOKEN_ENGINE_VERSION, analyze_token
from app.engines.wallet import analyze_wallet
from app.schemas.requests import AddressAnalyzeRequest, AddressLookupRequest
from app.services import history_store, report_store
from app.services.intel_lookup import IntelLookup, intel_coverage, lookup_intel

logger = logging.getLogger("chainguard.api.wallets")

router = APIRouter(prefix="/v1", tags=["analysis"])


def require_supported_chain(db: Session, chain_id: int) -> None:
    found = db.execute(text("SELECT 1 FROM chains WHERE chain_id = :c"), {"c": chain_id}).first()
    if found is None:
        raise ApiError(422, "unsupported_chain", f"Chain {chain_id} is not supported.")


@router.post("/wallets/analyze")
def analyze(
    body: AddressAnalyzeRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> dict[str, Any]:
    require_supported_chain(db, body.chain_id)
    cached = report_store.get_fresh(db, body.chain_id, "wallet", body.address, ENGINE_VERSION)
    if cached is not None:
        history_store.record(db, auth.client_id, cached)
        return cached
    report = analyze_wallet(
        body.chain_id,
        body.address,
        history_provider=providers.history,
        rpc=providers.rpc,
        explorer=providers.explorer,
        goplus=providers.goplus,
        intel_lookup=lambda cid, addrs: lookup_intel(db, cid, addrs),
    )
    report_store.save(db, report)
    history_store.record(db, auth.client_id, report)
    return report


def _address_type(rpc: Any, chain_id: int, address: str) -> str:
    res = rpc.get_code(chain_id, address)
    if res.status != "ok" or not isinstance(res.data, str):
        return "unknown"
    # An EIP-7702 wallet is an account with a delegation marker; the spec has no separate type.
    if res.data == "0x" or res.data.startswith("0xef0100"):
        return "eoa"
    return "contract"


@router.post("/addresses/lookup")
def lookup(
    body: AddressLookupRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> dict[str, Any]:
    require_supported_chain(db, body.chain_id)
    addresses = list(dict.fromkeys(body.addresses))  # dedupe, keep order

    intel: IntelLookup | None = None
    try:
        intel = lookup_intel(db, body.chain_id, addresses)
    except Exception as exc:
        logger.warning("intel lookup failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
    # Only a fully loaded set of lists counts as checked. Anything else is unavailable.
    checked = intel is not None and intel_coverage(intel).status == "completed"

    results = []
    for addr in addresses:
        hits = intel.hits.get(addr, ()) if intel is not None else ()
        results.append(
            {
                "address": addr,
                "address_type": _address_type(providers.rpc, body.chain_id, addr),
                "intel_hits": [
                    {
                        "source": h.source,
                        "category": h.category,
                        "list_version": h.list_version,
                        "fetched_at": h.fetched_at.isoformat() if h.fetched_at else None,
                    }
                    for h in hits
                ],
                "status": "checked" if checked else "unavailable",
            }
        )
    return {"chain_id": body.chain_id, "results": results}


@router.post("/tokens/analyze")
def analyze_token_endpoint(
    body: AddressAnalyzeRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> dict[str, Any]:
    require_supported_chain(db, body.chain_id)
    cached = report_store.get_fresh(db, body.chain_id, "token", body.address, TOKEN_ENGINE_VERSION)
    if cached is not None:
        history_store.record(db, auth.client_id, cached)
        return cached
    report = analyze_token(
        body.chain_id,
        body.address,
        rpc=providers.rpc,
        explorer=providers.explorer,
        goplus=providers.goplus,
        intel_lookup=lambda cid, addrs: lookup_intel(db, cid, addrs),
    )
    report_store.save(db, report)
    history_store.record(db, auth.client_id, report)
    return report
