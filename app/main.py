"""
FastAPI应用主入口
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.domain.research import (
    ResearchDuplicateError,
    ResearchNotFoundError,
    ResearchRevisionConflictError,
)
from app.exceptions import AppError, app_error_handler, invalid_request_handler, research_domain_error_handler, unhandled_exception_handler, request_validation_error_handler
from app.application.errors import InvalidRequestError
from app.lifecycle import lifespan
from app.rate_limit import limiter
from app.product import APP_VERSION
from app.runtime import RuntimeRole
from app.web import register_app_routes
from config import settings


def create_app(role: RuntimeRole | None = None) -> FastAPI:
    resolved_role = role or settings.APP_RUNTIME_ROLE
    app = FastAPI(
        title="OpenTrading",
        description="AI-Powered Crypto Trading Intelligence",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(ResearchNotFoundError, research_domain_error_handler)
    app.add_exception_handler(ResearchRevisionConflictError, research_domain_error_handler)
    app.add_exception_handler(ResearchDuplicateError, research_domain_error_handler)
    app.add_exception_handler(InvalidRequestError, invalid_request_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
    app.state.runtime_role = resolved_role
    register_app_routes(app, role=resolved_role)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        reload_dirs=["app", "config", "utils"],
        reload_excludes=["data/*", "logs/*", "frontend/dist/*"],
    )
