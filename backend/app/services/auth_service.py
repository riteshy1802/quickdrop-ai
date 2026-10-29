"""Argon2id passwords, revocable opaque sessions, database-coordinated login limits."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models import OpsLoginLimit, OpsSession, OpsUser

logger = logging.getLogger(__name__)
COOKIE = "quickdrop_ops_session"
hasher = PasswordHasher()


@lru_cache(maxsize=1)
def dummy_hash():
    return hasher.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def check_origin(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    own_origin = f"{request.url.scheme}://{request.url.netloc}"
    if (origin is not None and origin not in {own_origin, *get_settings().cors_origins}) or (
        request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Untrusted request origin")


def require_session_cookie(request: Request):
    check_origin(request)
    raw = request.cookies.get(COOKIE)
    if not raw or len(raw) > 128:
        raise HTTPException(401, "Ops authentication required")
    return raw


async def require_operator(
    raw: str = Depends(require_session_cookie), factory=Depends(get_session_factory)
):
    async with factory() as session:
        user = await session.scalar(
            select(OpsUser)
            .join(OpsSession, OpsSession.operator_id == OpsUser.id)
            .where(OpsSession.digest == digest(raw), OpsSession.expires_at > datetime.now(UTC))
        )
        if user is None:
            raise HTTPException(401, "Session invalid or expired")
        return user


Operator = Annotated[OpsUser, Depends(require_operator)]


async def login(factory, email, password, ip, old_cookie=None):
    settings = get_settings()
    now = datetime.now(UTC)
    keys = sorted([digest("email:" + email), digest("ip:" + ip)])
    async with factory() as session, session.begin():
        # All workers share these counters; proxy headers are deliberately not trusted.
        for key in keys:
            await session.execute(select(func.pg_advisory_xact_lock(int(key[:15], 16))))
        counters = []
        for key in keys:
            counter = await session.get(OpsLoginLimit, key)
            if counter is None:
                counter = OpsLoginLimit(key=key, attempts=0, window_start=now)
            elif counter.window_start <= now - timedelta(seconds=settings.ops_login_window_seconds):
                counter.attempts, counter.window_start = 0, now
            counters.append(counter)
        limited = any(c.attempts >= settings.ops_login_attempts for c in counters)
        if not limited:
            for counter in counters:
                session.add(counter)
                counter.attempts += 1
    if limited:
        raise HTTPException(
            429,
            "Too many login attempts",
            headers={"Retry-After": str(settings.ops_login_window_seconds)},
        )
    async with factory() as session, session.begin():
        user = await session.scalar(select(OpsUser).where(func.lower(OpsUser.email) == email))
        encoded = user.password_hash if user else await run_in_threadpool(dummy_hash)
        try:
            await run_in_threadpool(hasher.verify, encoded, password)
            valid = user is not None
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid:
            logger.info("ops_login_failed")
            raise HTTPException(401, "Invalid email or password")
        if hasher.check_needs_rehash(user.password_hash):
            user.password_hash = await run_in_threadpool(hasher.hash, password)
        if old_cookie:
            await session.execute(delete(OpsSession).where(OpsSession.digest == digest(old_cookie)))
        await session.execute(delete(OpsSession).where(OpsSession.expires_at <= now))
        raw = secrets.token_urlsafe(32)
        session.add(
            OpsSession(
                digest=digest(raw),
                operator_id=user.id,
                expires_at=now + timedelta(seconds=settings.ops_session_seconds),
            )
        )
        logger.info("ops_login operator_id=%s", user.id)
        return user, raw


async def logout(factory, raw, operator):
    async with factory() as session, session.begin():
        await session.execute(delete(OpsSession).where(OpsSession.digest == digest(raw)))
    logger.info("ops_logout operator_id=%s", operator.id)


async def seed_admin(session, email, password):
    email = email.strip().lower()
    if "@" not in email or len(email) > 320 or len(password) < 12 or len(password) > 1024:
        raise ValueError("Configure a valid admin email and a password of 12–1024 characters")
    await session.execute(
        select(func.pg_advisory_xact_lock(int(digest("admin:" + email)[:15], 16)))
    )
    user = await session.scalar(select(OpsUser).where(func.lower(OpsUser.email) == email))
    if user is not None:
        return user, False
    user = OpsUser(email=email, password_hash=await run_in_threadpool(hasher.hash, password))
    session.add(user)
    await session.flush()
    return user, True
