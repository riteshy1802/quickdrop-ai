"""QuickDrop API. Start with uv run uvicorn app.main:app --port 8000."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api import auth, health, messages, ops_pending, realtime, riders, trace
from app.api.ui import conversations, demo, ops, ops_cases, ops_conversations
from app.core.config import get_settings
from app.core.database import get_engine
from app.integrations.payswift import get_payswift_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No migrations or seeds at startup. Release an initialized pool on shutdown.
    try:
        yield
    finally:
        from app.realtime.publisher import drain

        await drain()
        if get_payswift_client.cache_info().currsize:
            await get_payswift_client().aclose()
            get_payswift_client.cache_clear()
        if get_engine.cache_info().currsize:
            await get_engine().dispose()


def error_response(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                **extra,
            }
        },
    )


def create_app() -> FastAPI:
    app = FastAPI(title="QuickDrop AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        response = error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [
            {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(
            422, "validation_error", "Invalid request parameters", details=details
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.warning("Database request failed (%s)", type(exc).__name__)
        return error_response(503, "database_unavailable", "Database unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unexpected request failure (%s)", type(exc).__name__)
        return error_response(500, "internal_error", "Internal server error")

    app.include_router(health.router)
    app.include_router(riders.router)
    for router in (
        auth.router,
        realtime.router,
        demo.router,
        ops_cases.router,
        ops_conversations.router,
        messages.router,
        trace.router,
        ops_pending.router,
        conversations.router,
        ops.router,
    ):
        app.include_router(router)
    return app


app = create_app()
