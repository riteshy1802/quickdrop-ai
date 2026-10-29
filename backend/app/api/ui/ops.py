from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.ops_pending import pending_response
from app.api.riders import Limit, Offset, Session
from app.api.ui.conversations import paginated
from app.core.database import get_session_factory
from app.integrations.payswift import PaySwiftClient, get_payswift_client
from app.repositories import conversations, disputes, messages, ops, ops_queue
from app.repositories.payment_jobs import PaymentBusy
from app.schemas import Page
from app.schemas.conversations import (
    ConversationResponse,
    ConversationStatus,
    DisputeResponse,
    HandlingMode,
    MessageResponse,
)
from app.schemas.ops import (
    CaseResponse,
    OverviewResponse,
    PaymentStatus,
    PayoutResponse,
    QueueStatus,
)
from app.schemas.traces import InternalTrace, TraceType
from app.services import trace_service
from app.services.auth_service import require_operator
from app.services.conversation_service import message_response, summary
from app.services.payment_worker import reconcile_intent

router = APIRouter(
    prefix="/ui/ops", tags=["Ops workspace"], dependencies=[Depends(require_operator)]
)


def require_row(row, label):
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row


def case_response(row):
    queue, dispute = row
    return {
        **pending_response(row),
        "dispute_id": dispute.id,
        "conversation_id": dispute.conversation_id,
        "status": queue.status,
        "claimed_amount": dispute.claimed_amount,
        "verified_amount": dispute.verified_amount,
        "resolved_at": queue.resolved_at,
        "assigned_to": queue.assigned_to,
        "decision_note": queue.decision_note,
    }


def payout_response(row):
    payout, conversation_id = row
    return {
        "id": payout.id,
        "dispute_id": payout.dispute_id,
        "rider_id": payout.rider_id,
        "conversation_id": conversation_id,
        "amount_rupees": payout.amount,
        "status": payout.status,
        "initiation": "AUTO" if payout.payment_type == "AUTO" else "HUMAN_APPROVED",
        "provider_id": payout.provider_payout_id,
        "retry_count": payout.retry_count,
        "next_retry_at": payout.next_retry_at,
        "reconciled_at": payout.last_reconciled_at,
        "created_at": payout.created_at,
        "updated_at": payout.updated_at,
    }


@router.get("/overview", response_model=OverviewResponse)
async def overview(session: Session):
    return await ops.overview(session)


@router.get("/conversations", response_model=Page[ConversationResponse])
async def list_conversations(
    session: Session,
    rider_id: str | None = None,
    handling_mode: HandlingMode | None = None,
    status: ConversationStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows, total = await conversations.list_conversations(
        session,
        rider_id=rider_id,
        handling_mode=handling_mode,
        status=status,
        limit=limit,
        offset=offset,
    )
    return paginated([summary(row) for row in rows], total, limit, offset)


class WorkspaceThread(ConversationResponse):
    # Detail uses bounded collections. Dedicated endpoints provide further pages.
    messages: Page[MessageResponse]
    disputes: Page[DisputeResponse]


@router.get("/conversations/{identifier}", response_model=WorkspaceThread)
async def get_conversation(
    identifier: UUID, session: Session, limit: Limit = 50, offset: Offset = 0
):
    row = require_row(await conversations.get(session, identifier), "Conversation")
    history, count = await messages.history(
        session, identifier, internal=True, limit=limit, offset=offset
    )
    cases, case_count = await disputes.for_conversation(
        session, identifier, limit=limit, offset=offset
    )
    return {
        **summary(row),
        "messages": paginated([message_response(m) for m in history], count, limit, offset),
        "disputes": paginated(cases, case_count, limit, offset),
    }


@router.get("/cases", response_model=Page[CaseResponse])
async def list_cases(
    session: Session,
    rider_id: str | None = None,
    status: QueueStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows, total = await ops_queue.list_cases(
        session, rider_id=rider_id, status=status, limit=limit, offset=offset
    )
    return paginated([case_response(row) for row in rows], total, limit, offset)


@router.get("/cases/{identifier}", response_model=CaseResponse)
async def get_case(identifier: UUID, session: Session):
    return case_response(require_row(await ops_queue.get_case(session, identifier), "Case"))


@router.get("/payouts", response_model=Page[PayoutResponse])
async def list_payouts(
    session: Session,
    rider_id: str | None = None,
    status: PaymentStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows, total = await ops.list_payouts(
        session, rider_id=rider_id, status=status, limit=limit, offset=offset
    )
    return paginated([payout_response(row) for row in rows], total, limit, offset)


@router.get("/payouts/{identifier}", response_model=PayoutResponse)
async def get_payout(identifier: UUID, session: Session):
    return payout_response(require_row(await ops.get_payout(session, identifier), "Payout"))


@router.get("/traces", response_model=Page[InternalTrace])
async def list_traces(
    session: Session,
    rider_id: str | None = None,
    conversation_id: UUID | None = None,
    type: TraceType | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows, total = await trace_service.retrieve(
        session,
        rider_id=rider_id,
        conversation_id=conversation_id,
        event_type=type,
        limit=limit,
        offset=offset,
    )
    return paginated(
        [
            {
                **trace_service.event(trace),
                "id": trace.id,
                "conversation_id": trace.conversation_id,
                "rider_id": rider,
            }
            for trace, rider in rows
        ],
        total,
        limit,
        offset,
    )


@router.post("/payouts/{identifier}/reconcile", response_model=PayoutResponse)
async def reconcile_payout(
    identifier: UUID,
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    client: Annotated[PaySwiftClient, Depends(get_payswift_client)],
):
    try:
        await reconcile_intent(factory, client, identifier)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Payout not found") from exc
    except PaymentBusy as exc:
        raise HTTPException(status_code=409, detail="Payout is currently being processed") from exc
    async with factory() as session:
        return payout_response(require_row(await ops.get_payout(session, identifier), "Payout"))
