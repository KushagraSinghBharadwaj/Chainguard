"""Transaction analysis endpoints. Read-only: never signs or sends."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_client
from app.api.providers_dep import Providers, get_providers
from app.api.wallets import require_supported_chain
from app.db.session import get_db, get_engine
from app.engines.tx import analyze_transaction, analyze_transaction_steps
from app.api.history import router as history_router
from app.services import history_store
from app.services.intel_lookup import lookup_intel

logger = logging.getLogger("chainguard.api.tx")

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
    report = analyze_transaction(
        body.chain_id, body.to, body.data,
        rpc=providers.rpc, explorer=providers.explorer, goplus=providers.goplus,
        intel_lookup=lambda cid, addrs: lookup_intel(db, cid, addrs),
    )
    history_store.record(db, auth.client_id, report)
    return report


def _line(event: str, payload: dict[str, Any]) -> str:
    body = {"event": "report", "report": payload} if event == "report" else {"event": event, **payload}
    return json.dumps(jsonable_encoder(body)) + "\n"


@router.post("/transactions/analyze/stream")
def analyze_tx_stream(
    body: TxAnalyzeRequest,
    auth: AuthContext = Depends(require_client),
    db: Session = Depends(get_db),
    providers: Providers = Depends(get_providers),
) -> StreamingResponse:
    """Same analysis, sent as one JSON line per event so a client can show each check as it runs."""
    require_supported_chain(db, body.chain_id)
    client_id = auth.client_id

    def events():
        try:
            # A separate session: the request-scoped one may be closed before the stream ends.
            with Session(get_engine()) as stream_db:
                for kind, payload in analyze_transaction_steps(
                    body.chain_id, body.to, body.data,
                    rpc=providers.rpc, explorer=providers.explorer, goplus=providers.goplus,
                    intel_lookup=lambda cid, addrs: lookup_intel(stream_db, cid, addrs),
                ):
                    if kind == "report":
                        history_store.record(stream_db, client_id, payload)
                    yield _line(kind, payload)
        except Exception as exc:
            logger.warning("stream failed", extra={"extra_fields": {"error_class": type(exc).__name__}})
            yield _line("error", {"message": "The analysis failed on the server."})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


router.include_router(history_router)