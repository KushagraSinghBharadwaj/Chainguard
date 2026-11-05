import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("chainguard.errors")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _envelope(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers=headers,
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return _envelope(request, exc.status_code, exc.code, exc.message, exc.headers)


async def database_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    # Error class only: the message can contain connection details.
    logger.warning(
        "database error",
        extra={"extra_fields": {"error_class": type(exc).__name__}},
    )
    return _envelope(request, 503, "database_unavailable", "Database is unavailable.")


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Field names only: never echo the submitted values back.
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
    return _envelope(request, 422, "invalid_request", "Invalid request: " + ", ".join(fields))
