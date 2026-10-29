"""Temporary internal read guard, disabled unless explicitly enabled locally."""

from fastapi import HTTPException, Request

from app.core.config import get_settings


def require_local_development(request: Request) -> None:
    from app.core.demo import cookie_name, require_demo

    rider_id = request.path_params.get("rider_id") or (
        request.query_params.get("rider_id") if "query_string" in request.scope else None
    )
    if rider_id and request.cookies.get(cookie_name(rider_id)):
        require_demo(request, rider_id)
        return
    settings = get_settings()
    if (
        settings.app_env != "development"
        or not settings.enable_local_internal_reads
        or request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
    ):
        raise HTTPException(status_code=403, detail="Internal reads disabled")
