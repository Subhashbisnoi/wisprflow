"""Global exception handlers producing a consistent error envelope."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import request_id_var

logger = logging.getLogger("app.errors")


def _envelope(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id_var.get(),
            }
        },
    )


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    log = logger.warning if exc.status_code < 500 else logger.error
    log("request failed", extra={"error_code": exc.code, "status": exc.status_code})
    return _envelope(exc.status_code, exc.code, exc.message, exc.details)


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return _envelope(422, "validation_error", "Some fields are invalid.", details)


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = {401: "not_authenticated", 404: "not_found", 405: "method_not_allowed"}.get(
        exc.status_code, HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
    )
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return _envelope(exc.status_code, code, message)


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return _envelope(500, "internal_error", "Something went wrong. Please try again.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
