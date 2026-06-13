from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_logger = logging.getLogger("api_gateway.error")


def error_body(code: str, message: str) -> dict:
    return {
        "error_code": code,
        "message": message,
        "correlation_id": str(uuid.uuid4()),
    }


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    msg = "; ".join(f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", msg))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = {404: "NOT_FOUND", 409: "CONFLICT", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}.get(
        exc.status_code, "ERROR"
    )
    return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Logs the full traceback and returns
    the same {error_code, message, correlation_id} shape so the front-end can
    parse it. Without this, Starlette's default 500 response is bare
    text/plain 'Internal Server Error' with no traceback captured server-side.
    """
    _logger.exception(
        "unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"),
    )
