from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Dispute, OpsQueue, PaymentIntent
from app.repositories.pagination import page


async def overview(session: AsyncSession):
    def count(model, *conditions):
        return select(func.count()).select_from(model).where(*conditions).scalar_subquery()

    confirmed = (
        select(func.coalesce(func.sum(PaymentIntent.amount), 0))
        .where(
            PaymentIntent.status == "SUCCEEDED",
            PaymentIntent.provider_payout_id.is_not(None),
            PaymentIntent.last_reconciled_at.is_not(None),
        )
        .scalar_subquery()
    )
    values = (
        await session.execute(
            select(
                count(Dispute),
                count(
                    OpsQueue,
                    OpsQueue.type == "approval",
                    OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
                    OpsQueue.resolved_at.is_(None),
                ),
                count(
                    OpsQueue,
                    OpsQueue.type == "escalation",
                    OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
                    OpsQueue.resolved_at.is_(None),
                ),
                count(
                    Conversation,
                    Conversation.handling_mode == "HUMAN",
                    Conversation.status != "RESOLVED",
                ),
                confirmed,
                count(
                    PaymentIntent, PaymentIntent.status.in_(("FAILED", "UNKNOWN", "NEEDS_REVIEW"))
                ),
            )
        )
    ).one()
    keys = (
        "total_disputes",
        "pending_approvals",
        "open_escalations",
        "human_conversations",
        "confirmed_payment_amount",
        "payment_exceptions",
    )
    result = dict(zip(keys, values, strict=True))
    result["confirmed_payment_amount"] = Decimal(result["confirmed_payment_amount"])
    return result


def payouts():
    return select(PaymentIntent, Dispute.conversation_id).join(
        Dispute, Dispute.id == PaymentIntent.dispute_id
    )


async def list_payouts(session, *, rider_id=None, status=None, limit=50, offset=0):
    statement = payouts()
    if rider_id is not None:
        statement = statement.where(PaymentIntent.rider_id == rider_id)
    if status is not None:
        statement = statement.where(PaymentIntent.status == status)
    return await page(
        session,
        statement.order_by(PaymentIntent.created_at, PaymentIntent.id),
        limit=limit,
        offset=offset,
    )


async def get_payout(session, identifier):
    return (await session.execute(payouts().where(PaymentIntent.id == identifier))).one_or_none()
