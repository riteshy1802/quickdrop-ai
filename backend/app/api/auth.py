from fastapi import APIRouter, Depends, Request, Response

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.schemas.auth import LoginInput, OperatorResponse
from app.services import auth_service
from app.services.auth_service import Operator

router = APIRouter(prefix="/auth", tags=["Ops authentication"])


@router.post("/login", response_model=OperatorResponse)
async def login(
    payload: LoginInput, request: Request, response: Response, factory=Depends(get_session_factory)
):
    auth_service.check_origin(request)
    user, raw = await auth_service.login(
        factory,
        payload.email,
        payload.password.get_secret_value(),
        request.client.host if request.client else "unknown",
        request.cookies.get(auth_service.COOKIE),
    )
    settings = get_settings()
    response.set_cookie(
        auth_service.COOKIE,
        raw,
        httponly=True,
        samesite="strict",
        secure=settings.ops_cookie_secure
        or settings.app_env != "development"
        or request.url.scheme == "https",
        max_age=settings.ops_session_seconds,
    )
    response.headers["Cache-Control"] = "no-store"
    return user


@router.get("/me", response_model=OperatorResponse)
async def me(operator: Operator, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return operator


@router.post("/logout", status_code=204)
async def logout(operator: Operator, request: Request, factory=Depends(get_session_factory)):
    await auth_service.logout(factory, request.cookies[auth_service.COOKIE], operator)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(auth_service.COOKIE, httponly=True, samesite="strict")
    return response
