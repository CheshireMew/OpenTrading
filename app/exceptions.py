from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.errors import InvalidRequestError
from app.contracts.dto.errors import ApiErrorResponse
from app.domain.portfolios import (
    PortfolioCollectionMismatchError,
    PortfolioNotFoundError,
    PortfolioRevisionConflictError,
)
from utils.logger import logger


@dataclass(slots=True)
class AppError(Exception):
    detail: str
    status_code: int = 400


class BadRequestError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=400)


class NotFoundError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=404)


class ConflictError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class ServiceUnavailableError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=503)


async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=ApiErrorResponse(detail=exc.detail).model_dump())


async def invalid_request_handler(_request: Request, exc: InvalidRequestError):
    return JSONResponse(status_code=400, content=ApiErrorResponse(detail=str(exc)).model_dump())


async def request_validation_error_handler(_request: Request, exc: RequestValidationError):
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(
            str(item)
            for item in error.get("loc", ())
            if item not in {"body", "query", "path"}
        )
        message = str(error.get("msg") or "Invalid value")
        messages.append(f"{location}: {message}" if location else message)
    detail = "; ".join(messages) or "Request validation failed"
    return JSONResponse(
        status_code=422,
        content=ApiErrorResponse(detail=detail).model_dump(),
    )


async def portfolio_domain_error_handler(_request: Request, exc: Exception):
    if isinstance(exc, PortfolioNotFoundError):
        status_code = 404
    elif isinstance(exc, (PortfolioRevisionConflictError, PortfolioCollectionMismatchError)):
        status_code = 409
    else:
        status_code = 500
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(detail=str(exc)).model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled: {request.method} {request.url} - {exc}", exc_info=True)
    return JSONResponse(status_code=500, content=ApiErrorResponse(detail="Internal server error").model_dump())
