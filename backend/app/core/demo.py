"""Signed demo identities are explicit simulator context, not production rider authentication."""

import hashlib

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

COOKIE_AGE = 28800


def signer():
    return URLSafeTimedSerializer(
        get_settings().demo_session_secret.get_secret_value(), salt="quickdrop-demo-rider"
    )


def cookie_name(rider_id):
    return "quickdrop_demo_" + hashlib.sha256(rider_id.encode()).hexdigest()[:16]


def require_demo(request: Request, rider_id: str):
    if not get_settings().enable_demo_workspace:
        raise HTTPException(403, "Rider simulator disabled")
    try:
        identity = signer().loads(
            request.cookies.get(cookie_name(rider_id), ""), max_age=COOKIE_AGE
        )
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Select a demo rider first") from None
    if identity != rider_id:
        raise HTTPException(403, "Rider context does not match")
    return rider_id
