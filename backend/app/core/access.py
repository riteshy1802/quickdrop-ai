"""Temporary internal read guard, disabled unless explicitly enabled locally."""

from fastapi import HTTPException, Request

from app.core.config import get_settings


def require_local_development(request: Request) -> None:
    settings = get_settings()
    if (
        settings.app_env != "development"
        or not settings.enable_local_internal_reads
        or request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
    ):
        raise HTTPException(status_code=403, detail="Internal reads disabled")
