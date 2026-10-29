"""Real HTTP/session and concurrent Ops checks, using only a disposable database."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_payments_database import create_case
from test_payments_database import provider as provider

from app.agent.state import Extraction
from app.agent.tools import AgentTools, OwnershipLost
from app.core.access import require_local_development
from app.core.config import Settings
from app.core.database import get_db_session, get_session_factory
from app.integrations.payswift import get_payswift_client
from app.main import create_app
from app.models import (
    AgentTrace,
    Conversation,
    Dispute,
    DisputeItem,
    Message,
    OpsLoginLimit,
    OpsQueue,
    OpsSession,
    OpsUser,
    PaymentIntent,
    PayoutLine,
    Rider,
    Trip,
)
from app.schemas.messages import IncomingMessage
from app.services import auth_service, message_service, ops_case_service
from app.services.payment_authorization import authorize_payment

pytestmark = pytest.mark.database
PASSWORD = "test-only-strong-password"


@pytest_asyncio.fixture
async def ops_api(database_url, provider, monkeypatch):
    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    rider = "O" + uuid4().hex[:20]
    settings = Settings(_env_file=None, ops_login_attempts=20)
    monkeypatch.setattr(auth_service, "get_settings", lambda: settings)
    async with factory() as session, session.begin():
        users = []
        for _ in range(2):
            user, _ = await auth_service.seed_admin(
                session, uuid4().hex + "@test.invalid", PASSWORD
            )
            users.append(user)
        session.add(Rider(rider_id=rider, name="Ops test", city="Test", joined_on=date(2026, 1, 1)))
    client, mock = provider
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_payswift_client] = lambda: client
    app.dependency_overrides[require_local_development] = lambda: None

    async def dependency():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield SimpleNamespace(
            http=http,
            factory=factory,
            rider=rider,
            users=users,
            app=app,
            client=client,
            mock=mock,
            settings=settings,
        )
    async with factory() as session, session.begin():
        conversations = select(Conversation.id).where(Conversation.rider_id == rider)
        disputes = select(Dispute.id).where(Dispute.rider_id == rider)
        for model, condition in (
            (OpsQueue, OpsQueue.dispute_id.in_(disputes)),
            (PaymentIntent, PaymentIntent.rider_id == rider),
            (DisputeItem, DisputeItem.dispute_id.in_(disputes)),
            (Dispute, Dispute.rider_id == rider),
            (AgentTrace, AgentTrace.conversation_id.in_(conversations)),
            (Message, Message.conversation_id.in_(conversations)),
            (Conversation, Conversation.rider_id == rider),
            (PayoutLine, PayoutLine.rider_id == rider),
            (Trip, Trip.rider_id == rider),
            (Rider, Rider.rider_id == rider),
            (OpsSession, OpsSession.operator_id.in_([u.id for u in users])),
            (OpsUser, OpsUser.id.in_([u.id for u in users])),
        ):
            await session.execute(delete(model).where(condition))
        await session.execute(delete(OpsLoginLimit))
    await engine.dispose()


async def login(env, index=0, http=None):
    response = await (http or env.http).post(
        "/auth/login",
        json={
            "email": env.users[index].email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response


async def conversation(env):
    async with env.factory() as session, session.begin():
        row = Conversation(rider_id=env.rider)
        session.add(row)
        await session.flush()
        return row.id


async def financial_case(env, amount=425):
    identifier, request = await create_case(env.factory, env.rider, amount)
    result = await authorize_payment(
        env.factory, env.client, identifier, request, source_data_complete=True
    )
    assert result.status == "APPROVAL_REQUIRED"
    async with env.factory() as session, session.begin():
        dispute = await session.get(Dispute, identifier)
        dispute.details = {"request": request.model_dump(mode="json")}
        return result.queue_id, dispute.conversation_id, identifier


async def escalation(env):
    identifier = await conversation(env)
    async with env.factory() as session, session.begin():
        dispute = Dispute(conversation_id=identifier, rider_id=env.rider, status="ESCALATED")
        session.add(dispute)
        await session.flush()
        case = OpsQueue(dispute_id=dispute.id, type="escalation", reason="Identity review")
        session.add(case)
        await session.flush()
        return case.id, identifier


async def assert_no_payment(env):
    assert not env.mock.posts
    async with env.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PaymentIntent)
                .where(PaymentIntent.rider_id == env.rider)
            )
            == 0
        )


async def test_authentication_sessions_cookie_flags_and_logout(ops_api):
    e = ops_api
    assert (await e.http.get("/auth/me")).status_code == 401
    assert (await e.http.post("/auth/logout")).status_code == 401
    assert (await e.http.post("/auth/login", json={})).status_code == 422
    for email in (e.users[0].email, "missing@test.invalid"):
        response = await e.http.post("/auth/login", json={"email": email, "password": "wrong"})
        assert (
            response.status_code == 401
            and response.json()["error"]["message"] == "Invalid email or password"
        )
    response = await login(e)
    assert set(response.json()) == {"id", "email"}
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    raw = e.http.cookies.get(auth_service.COOKIE)
    async with e.factory() as session:
        stored = await session.get(OpsSession, auth_service.digest(raw))
        assert stored and stored.digest != raw
        user = await session.get(OpsUser, e.users[0].id)
        assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    assert (await e.http.get("/auth/me")).json()["id"] == str(e.users[0].id)
    assert (await e.http.post("/auth/logout")).status_code == 204
    assert (
        await e.http.get("/auth/me", headers={"Cookie": f"{auth_service.COOKIE}={raw}"})
    ).status_code == 401


async def test_expiration_rotation_and_idempotent_admin_seed(ops_api):
    e = ops_api
    async with e.factory() as session, session.begin():
        user, created = await auth_service.seed_admin(
            session, e.users[0].email.upper(), "another-valid-password"
        )
        assert not created and user.id == e.users[0].id
    await login(e)
    old = e.http.cookies.get(auth_service.COOKIE)
    await login(e)
    async with e.factory() as session, session.begin():
        assert await session.get(OpsSession, auth_service.digest(old)) is None
        current = await session.get(
            OpsSession, auth_service.digest(e.http.cookies.get(auth_service.COOKIE))
        )
        current.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await e.http.get("/auth/me")).status_code == 401


async def test_rate_limit_and_browser_origin(ops_api):
    e = ops_api
    e.settings.ops_login_attempts = 2
    for _ in range(2):
        assert (
            await e.http.post("/auth/login", json={"email": e.users[0].email, "password": "bad"})
        ).status_code == 401
    assert (
        await e.http.post("/auth/login", json={"email": e.users[1].email, "password": PASSWORD})
    ).status_code == 429
    async with e.factory() as session, session.begin():
        for row in await session.scalars(select(OpsLoginLimit)):
            row.window_start -= timedelta(seconds=1000)
    await login(e)
    identifier = await conversation(e)
    response = await e.http.post(
        f"/ui/ops/conversations/{identifier}/takeover", headers={"Origin": "https://evil.invalid"}
    )
    assert response.status_code == 403


async def test_secure_cookie_on_https(ops_api):
    e = ops_api
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=e.app), base_url="https://test"
    ) as https:
        response = await login(e, http=https)
        assert "Secure" in response.headers["set-cookie"]
        assert (await https.get("/auth/me")).status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/ui/ops/overview"),
        ("GET", "/ui/ops/conversations"),
        ("GET", "/ui/ops/conversations/{id}"),
        ("GET", "/ui/ops/cases"),
        ("GET", "/ui/ops/cases/{id}"),
        ("GET", "/ui/ops/payouts"),
        ("GET", "/ui/ops/payouts/{id}"),
        ("GET", "/ui/ops/traces"),
        ("POST", "/ui/ops/payouts/{id}/reconcile"),
        *[("POST", "/ui/ops/cases/{id}/" + a) for a in ("approve", "reject", "assign", "resolve")],
        *[
            ("POST", "/ui/ops/conversations/{id}/" + a)
            for a in ("takeover", "handoff", "resolve", "messages", "notes")
        ],
    ],
)
async def test_every_ops_endpoint_requires_auth(ops_api, method, path):
    response = await ops_api.http.request(method, path.replace("{id}", str(uuid4())), json={})
    assert response.status_code == 401, response.text


async def test_public_assignment_routes_are_unauthenticated(ops_api, monkeypatch):
    e = ops_api
    e.app.dependency_overrides.pop(require_local_development)
    assert (await e.http.get("/ops/pending")).status_code == 200
    assert (await e.http.get("/trace/" + e.rider)).status_code == 200
    monkeypatch.setattr(
        message_service,
        "run_handler",
        AsyncMock(return_value="Saved"),
    )
    response = await e.http.post(
        "/messages",
        json={
            "message_id": uuid4().hex,
            "rider_id": e.rider,
            "text": "hello",
            "received_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 200 and "reply" in response.json()


async def test_exact_425_approval_is_atomic_and_does_not_pay(ops_api, monkeypatch):
    e = ops_api
    await login(e)
    case, _, dispute = await financial_case(e)
    monkeypatch.setattr(ops_case_service, "source_coverage", AsyncMock(return_value=True))
    response = await e.http.post(f"/ui/ops/cases/{case}/approve")
    assert response.status_code == 200, response.text
    assert not response.json()["payment_confirmed"]
    async with e.factory() as session:
        intent = await session.get(PaymentIntent, UUID(response.json()["payment_intent_id"]))
        assert (
            intent.amount == 425
            and intent.payment_type == "OPS_APPROVED"
            and intent.status == "PENDING"
        )
        assert (await session.get(OpsQueue, case)).assigned_to == e.users[0].id
        assert (await session.get(Dispute, dispute)).status == "PAYMENT_PENDING"
        assert await session.scalar(
            select(AgentTrace.id).where(AgentTrace.name == "ops_case_approve")
        )
    assert (await e.http.post(f"/ui/ops/cases/{case}/approve")).status_code == 409
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/reject", json={"reason": "too late"})
    ).status_code == 409
    assert not e.mock.posts


async def test_concurrent_approvals_have_one_winner(ops_api, monkeypatch):
    e = ops_api
    case, _, _ = await financial_case(e)
    monkeypatch.setattr(ops_case_service, "source_coverage", AsyncMock(return_value=True))
    await login(e)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=e.app), base_url="http://test"
    ) as other:
        await login(e, 1, other)
        responses = await asyncio.gather(
            e.http.post(f"/ui/ops/cases/{case}/approve"),
            other.post(f"/ui/ops/cases/{case}/approve"),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    async with e.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PaymentIntent)
                .where(PaymentIntent.rider_id == e.rider)
            )
            == 1
        )
    assert not e.mock.posts


@pytest.mark.parametrize("problem", ["source", "amount", "settled", "unknown", "provider", "scope"])
async def test_unsafe_approval_rolls_back(ops_api, monkeypatch, problem):
    e = ops_api
    await login(e)
    case, _, dispute = await financial_case(e)
    monkeypatch.setattr(
        ops_case_service, "source_coverage", AsyncMock(return_value=problem != "source")
    )
    async with e.factory() as session, session.begin():
        if problem == "amount":
            (await session.get(OpsQueue, case)).amount = 424
        if problem == "settled":
            (await session.get(Dispute, dispute)).status = "RESOLVED"
        if problem == "scope":
            (await session.get(Dispute, dispute)).details = {}
        if problem == "unknown":
            session.add(
                PaymentIntent(
                    dispute_id=dispute,
                    rider_id=e.rider,
                    amount=425,
                    payment_type="OPS_APPROVED",
                    status="UNKNOWN",
                    idempotency_key=uuid4().hex,
                )
            )
    if problem == "provider":
        e.mock.bad_ledger = True
    response = await e.http.post(f"/ui/ops/cases/{case}/approve")
    assert response.status_code == 409, response.text
    async with e.factory() as session:
        assert (await session.get(OpsQueue, case)).status == "PENDING"
    assert not e.mock.posts


async def test_rejection_requires_reason_and_cannot_repeat(ops_api):
    e = ops_api
    await login(e)
    case, _, dispute = await financial_case(e)
    for payload in ({}, {"reason": ""}, {"reason": "  "}):
        assert (await e.http.post(f"/ui/ops/cases/{case}/reject", json=payload)).status_code == 422
    response = await e.http.post(
        f"/ui/ops/cases/{case}/reject", json={"reason": "Reviewed; claim invalid"}
    )
    assert response.status_code == 200 and response.json()["status"] == "REJECTED"
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/reject", json={"reason": "again"})
    ).status_code == 409
    await assert_no_payment(e)


async def test_escalation_assignment_resolution_and_wrong_type(ops_api):
    e = ops_api
    await login(e)
    case, _ = await escalation(e)
    assert (await e.http.post(f"/ui/ops/cases/{case}/approve")).status_code == 409
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/reject", json={"reason": "No"})
    ).status_code == 409
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/resolve", json={"reason": "Reviewed"})
    ).status_code == 409
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/assign", json={"operator_id": str(uuid4())})
    ).status_code == 404
    response = await e.http.post(f"/ui/ops/cases/{case}/assign")
    assert response.status_code == 200 and response.json()["assigned_to"] == str(e.users[0].id)
    assert (await e.http.post(f"/ui/ops/cases/{case}/assign")).status_code == 409
    await login(e, 1)
    assert (
        await e.http.post(f"/ui/ops/cases/{case}/resolve", json={"reason": "Reviewed"})
    ).status_code == 409
    await login(e)
    response = await e.http.post(
        f"/ui/ops/cases/{case}/resolve", json={"reason": "Identity verified against records"}
    )
    assert response.status_code == 200 and response.json()["status"] == "RESOLVED"
    await assert_no_payment(e)


async def test_takeover_messages_notes_privacy_and_safe_handback(ops_api):
    e = ops_api
    await login(e)
    identifier = await conversation(e)
    base = f"/ui/ops/conversations/{identifier}"
    content = {"text": "Human support reply", "client_request_id": str(uuid4())}
    assert (await e.http.post(base + "/messages", json=content)).status_code == 409
    assert (await e.http.post(base + "/takeover")).status_code == 200
    assert (await e.http.post(base + "/takeover")).status_code == 409
    response = await e.http.post(base + "/messages", json=content)
    assert response.status_code == 201, response.text
    assert response.json()["operator_id"] == str(e.users[0].id)
    assert (await e.http.post(base + "/messages", json=content)).json()["id"] == response.json()[
        "id"
    ]
    assert (
        await e.http.post(base + "/messages", json={**content, "text": "Changed"})
    ).status_code == 409
    note = {"text": "Private identity investigation note", "client_request_id": str(uuid4())}
    assert (await e.http.post(base + "/notes", json=note)).status_code == 201
    private = (await e.http.get(base)).json()["messages"]
    assert private["total"] == 2
    public = await e.http.get(
        f"/ui/conversations/{identifier}/messages", params={"rider_id": e.rider}
    )
    assert public.json()["total"] == 1 and note["text"] not in public.text
    assert note["text"] not in (await e.http.get("/trace/" + e.rider)).text
    assert (
        note["text"]
        not in (await e.http.get("/ui/conversations", params={"rider_id": e.rider})).text
    )
    await login(e, 1)
    assert (
        await e.http.post(base + "/messages", json={**content, "client_request_id": str(uuid4())})
    ).status_code == 409
    assert (await e.http.post(base + "/handoff")).status_code == 409
    await login(e)
    result = await e.http.post(base + "/handoff")
    assert result.status_code == 200 and result.json()["handling_mode"] == "AI"
    await assert_no_payment(e)


@pytest.mark.parametrize(
    "blocker",
    ["approval", "escalation", "identity", "security", "investigation", "unknown", "needs_review"],
)
async def test_handback_and_resolution_blockers(ops_api, blocker):
    e = ops_api
    await login(e)
    if blocker == "approval":
        _, identifier, _ = await financial_case(e)
    elif blocker == "escalation":
        _, identifier = await escalation(e)
    else:
        identifier = await conversation(e)
        async with e.factory() as session, session.begin():
            conv = await session.get(Conversation, identifier)
            if blocker in ("identity", "security"):
                conv.context = {blocker + "_concern": True}
            else:
                dispute = Dispute(
                    conversation_id=identifier,
                    rider_id=e.rider,
                    status="INVESTIGATING" if blocker == "investigation" else "VERIFIED",
                )
                session.add(dispute)
                await session.flush()
                if blocker in {"unknown", "needs_review"}:
                    session.add(
                        PaymentIntent(
                            dispute_id=dispute.id,
                            rider_id=e.rider,
                            amount=25,
                            payment_type="OPS_APPROVED",
                            status="UNKNOWN" if blocker == "unknown" else "NEEDS_REVIEW",
                            idempotency_key=uuid4().hex,
                        )
                    )
    base = f"/ui/ops/conversations/{identifier}"
    assert (await e.http.post(base + "/takeover")).status_code == 200
    assert (await e.http.post(base + "/handoff")).status_code == 409
    assert (await e.http.post(base + "/resolve", json={"reason": "Reviewed"})).status_code == 409
    assert not e.mock.posts


async def test_resolution_creates_fresh_thread_for_next_rider_message(ops_api, monkeypatch):
    e = ops_api
    await login(e)
    identifier = await conversation(e)
    base = f"/ui/ops/conversations/{identifier}"
    assert (await e.http.post(base + "/takeover")).status_code == 200
    assert (
        await e.http.post(base + "/resolve", json={"reason": "Support review complete"})
    ).status_code == 200
    assert (await e.http.post(base + "/handoff")).status_code == 409
    monkeypatch.setattr(message_service, "run_handler", AsyncMock(return_value="New conversation"))
    response = await e.http.post(
        "/messages",
        json={
            "message_id": uuid4().hex,
            "rider_id": e.rider,
            "text": "New concern",
            "received_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 200
    async with e.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.rider_id == e.rider)
            )
            == 2
        )


async def test_takeover_fences_inflight_graph_even_after_handback(ops_api):
    from app.agent.graph import run_agent

    e = ops_api
    await login(e)
    payload = IncomingMessage(
        message_id=uuid4().hex, rider_id=e.rider, text="Hello", received_at=datetime.now(UTC)
    )
    claimed = await message_service.claim(e.factory, payload)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return Extraction(intent="other", language="en")

    task = asyncio.create_task(run_agent(e.factory, claimed, extractor=delayed))
    await asyncio.wait_for(entered.wait(), 3)
    base = f"/ui/ops/conversations/{claimed.conversation_id}"
    assert (await e.http.post(base + "/takeover")).status_code == 200
    assert (await e.http.post(base + "/handoff")).status_code == 200
    release.set()
    with pytest.raises(OwnershipLost):
        await task
    assert (
        await message_service.complete(e.factory, claimed, "Stale AI reply")
        == message_service.HUMAN_REPLY
    )
    async with e.factory() as session:
        assert not list(
            await session.scalars(
                select(Message).where(
                    Message.conversation_id == claimed.conversation_id, Message.sender_type == "AI"
                )
            )
        )
    await assert_no_payment(e)


async def test_human_mode_persists_incoming_and_suppresses_ai(ops_api, monkeypatch):
    e = ops_api
    await login(e)
    identifier = await conversation(e)
    await e.http.post(f"/ui/ops/conversations/{identifier}/takeover")
    handler = AsyncMock(side_effect=AssertionError("Must not run agent"))
    monkeypatch.setattr(message_service, "run_handler", handler)
    response = await e.http.post(
        "/messages",
        json={
            "message_id": uuid4().hex,
            "rider_id": e.rider,
            "text": "Still need help",
            "received_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 200 and response.json()["reply"] == message_service.HUMAN_REPLY
    handler.assert_not_awaited()
    assert "Still need help" in (await e.http.get(f"/ui/ops/conversations/{identifier}")).text


@pytest.mark.parametrize(
    "path",
    [
        "cases/{id}/approve",
        "cases/{id}/reject",
        "cases/{id}/assign",
        "cases/{id}/resolve",
        "conversations/{id}/takeover",
        "conversations/{id}/handoff",
        "conversations/{id}/resolve",
        "conversations/{id}/messages",
        "conversations/{id}/notes",
    ],
)
async def test_missing_resources(ops_api, path):
    await login(ops_api)
    response = await ops_api.http.post(
        "/ui/ops/" + path.replace("{id}", str(uuid4())),
        json={"reason": "reviewed"}
        if path.endswith(("/reject", "/resolve"))
        else {"text": "message", "client_request_id": str(uuid4())}
        if path.endswith(("/messages", "/notes"))
        else {},
    )
    assert response.status_code == 404, response.text


async def test_takeover_fences_payment_authorization_boundary(ops_api):
    e = ops_api
    await login(e)
    identifier, request = await create_case(e.factory, e.rider, 25)
    claimed = await message_service.claim(
        e.factory,
        IncomingMessage(
            message_id=uuid4().hex,
            rider_id=e.rider,
            text="Trip pay missing",
            received_at=datetime.now(UTC),
        ),
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def ledger(rider):
        entered.set()
        await release.wait()
        return ()

    tools = AgentTools(e.factory, claimed, client=SimpleNamespace(ledger=ledger))
    task = asyncio.create_task(tools.create_payment_intent(identifier, request, coverage=True))
    await asyncio.wait_for(entered.wait(), 3)
    assert (
        await e.http.post(f"/ui/ops/conversations/{claimed.conversation_id}/takeover")
    ).status_code == 200
    release.set()
    with pytest.raises(OwnershipLost):
        await task
    await assert_no_payment(e)


async def test_concurrent_human_message_retries_and_audit_events(ops_api):
    e = ops_api
    await login(e)
    identifier = await conversation(e)
    base = f"/ui/ops/conversations/{identifier}"
    replies = await asyncio.gather(e.http.post(base + "/takeover"), e.http.post(base + "/takeover"))
    assert sorted(r.status_code for r in replies) == [200, 409]
    payload = {"text": "Review completed", "client_request_id": str(uuid4())}
    replies = await asyncio.gather(
        *[e.http.post(base + "/messages", json=payload) for _ in range(2)]
    )
    assert all(r.status_code == 201 for r in replies)
    assert replies[0].json()["id"] == replies[1].json()["id"]
    assert (
        await e.http.post(
            base + "/notes", json={"text": "Private note", "client_request_id": str(uuid4())}
        )
    ).status_code == 201
    assert (await e.http.post(base + "/handoff")).status_code == 200
    async with e.factory() as session:
        events = list(
            await session.scalars(
                select(AgentTrace).where(AgentTrace.conversation_id == identifier)
            )
        )
        assert {t.name for t in events} == {
            "ops_takeover",
            "ops_human_message",
            "ops_internal_note",
            "ops_handoff",
        }
        for event in events:
            assert event.input["operator_id"] == str(e.users[0].id)
            assert event.created_at.tzinfo is not None
        assert len([t for t in events if t.name == "ops_human_message"]) == 1


async def test_concurrent_escalation_assignments_have_one_owner(ops_api):
    e = ops_api
    await login(e)
    case, _ = await escalation(e)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=e.app), base_url="http://test"
    ) as other:
        await login(e, 1, other)
        responses = await asyncio.gather(
            e.http.post(f"/ui/ops/cases/{case}/assign"), other.post(f"/ui/ops/cases/{case}/assign")
        )
    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_reference_425_claim_uses_real_csv_coverage(connection, seeded, provider):
    """No financial or coverage mocks: actual imported R016 reference claim."""
    from test_agent_graph import extracted

    from app.agent.graph import run_agent

    factory = async_sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    client, mock = provider
    payload = IncomingMessage(
        message_id=uuid4().hex,
        rider_id="R016",
        text="19 sept 5 orders missing",
        received_at="2026-09-23T09:05:00+05:30",
    )
    claimed = await message_service.claim(factory, payload)
    extraction = Extraction.model_validate(extracted("PAYOUT", dates=("19 sept",)))
    reply = await run_agent(
        factory, claimed, client=client, extractor=AsyncMock(return_value=extraction)
    )
    await message_service.complete(factory, claimed, reply)
    async with factory() as session, session.begin():
        user, _ = await auth_service.seed_admin(session, "reference@test.invalid", PASSWORD)
        case = await session.scalar(select(OpsQueue).where(OpsQueue.type == "approval"))
        assert case.amount == 425
        identifier = case.id
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_payswift_client] = lambda: client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        assert (
            await http.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        ).status_code == 200
        response = await http.post(f"/ui/ops/cases/{identifier}/approve")
        assert response.status_code == 200, response.text
    async with factory() as session:
        intent = await session.get(PaymentIntent, UUID(response.json()["payment_intent_id"]))
        assert intent.amount == 425 and intent.payment_type == "OPS_APPROVED"
    assert not mock.posts


async def test_payment_completion_preserves_human_control(ops_api, monkeypatch):
    from app.services.payment_worker import process_one

    e = ops_api
    await login(e)
    case, identifier, _ = await financial_case(e)
    monkeypatch.setattr(ops_case_service, "source_coverage", AsyncMock(return_value=True))
    assert (await e.http.post(f"/ui/ops/cases/{case}/approve")).status_code == 200
    base = f"/ui/ops/conversations/{identifier}"
    assert (await e.http.post(base + "/takeover")).status_code == 200
    assert await process_one(e.factory, e.client)
    async with e.factory() as session:
        conv = await session.get(Conversation, identifier)
        assert conv.handling_mode == "HUMAN" and conv.status == "HUMAN_HANDLING"
    assert (
        await e.http.post(base + "/resolve", json={"reason": "Confirmed payment and reviewed"})
    ).status_code == 200
