"""Transaction analysis endpoint. Read-only: never signs or sends."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_client
from app.api.providers_dep import Providers, get_providers
from app.api.wallets import require_supported_chain
from app.db.session import get_db
from app.engines.tx import analyze_transaction
from app.services.intel_lookup import lookup_intel

router = APIRouter(prefix="/v1", tags=["analysis"])


class TxAnalyzeRequest(BaseModel):
    chain_id: int
    to: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    data: str = Field(default="0x", pattern=r"^0x([0-9a-fA-F]{2})*$", max_length=20000)


@router.post("/transactions/analyze")
def analyze_tx_endpoint(
    body: TxAnalyzeRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> dict[str, Any]:
    require_supported_chain(db, body.chain_id)
    return analyze_transaction(
        body.chain_id, body.to, body.data,
        rpc=providers.rpc, explorer=providers.explorer, goplus=providers.goplus,
        intel_lookup=lambda cid, addrs: lookup_intel(db, cid, addrs),
    )
