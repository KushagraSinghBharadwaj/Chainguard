import logging
import time

from fastapi import FastAPI, Request

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("chainguard.http")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
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
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            },
        )
        return response

    app.include_router(health_router)
    return app


app = create_app()