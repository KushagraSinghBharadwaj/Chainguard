from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import uuid

from fastapi import FastAPI, Request

from app.api.history import router as history_router
from app.api.clients import router as clients_router
from app.api.health import router as health_router
from app.api.transactions import router as transactions_router
from app.api.wallets import router as wallets_router
from app.core.errors import ApiError, api_error_handler, database_error_handler, validation_error_handler
from app.core.config import get_settings
from app.core.logging import setup_logging
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("chainguard.http")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        request.state.request_id = uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled error",
                extra={"extra_fields": {"method": request.method, "path": request.url.path}},
            )
            raise
        logger.info(
            "request",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": request.url.path,  # query string deliberately not logged
                    "status": response.status_code,
                    "request_id": request.state.request_id,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            },
        )
        return response

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(OperationalError, database_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_middleware(CORSMiddleware, allow_origin_regex=r'^chrome-extension://[a-z]{32}$', allow_methods=['GET','POST'], allow_headers=['Authorization','Content-Type'])
    app.include_router(health_router)
    app.include_router(wallets_router)
    app.include_router(transactions_router)
    app.include_router(clients_router)
    app.include_router(history_router)
    return app


app = create_app()