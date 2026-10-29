"""Identity-bound tools. Model output never supplies identity, money, or approval authority."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from functools import wraps
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.agent.prompts import PROMPT_VERSION
from app.agent.tools.coverage import source_coverage
from app.integrations.payswift import ProviderUnavailable, get_payswift_client
from app.models import Conversation, Dispute, DisputeItem, Message, OpsQueue, PaymentIntent, Rider
from app.repositories import financial
from app.services import conversation_service, trace_service
from app.services.financial.reconciliation import reconcile
from app.services.financial.types import ClaimRequest, PaymentEvidence
from app.services.payment_authorization import (
    EvidenceUnavailable,
    approval_queue,
    authorize_payment,
    provider_evidence,
)
from app.services.payment_reconciliation import match_payout, reference_for


class OwnershipLost(Exception):
    pass


class EvidenceConflict(ValueError):
    """A known ownership/date conflict, rather than an operational tool failure."""


def audited_tool(method):
    @wraps(method)
    async def call(self, *args, **kwargs):
        try:
            return await method(self, *args, **kwargs)
        except (OwnershipLost, EvidenceConflict):
            raise
        except Exception as exc:
            # Never log raw exceptions: provider bodies may contain rider data/secrets.
            logging.getLogger(__name__).warning(
                "Agent tool failed tool=%s error_type=%s", method.__name__, type(exc).__name__
            )
            await self.audit(
                "agent_tool_failed",
                {"tool": method.__name__, "error_type": type(exc).__name__, "retryable": True},
                event_type="error",
            )
            raise

    return call


class AgentTools:
    def __init__(self, factory, claimed, client=None):
        self.factory, self.claimed = factory, claimed
        self.rider_id = claimed.rider_id
        self.client = client or get_payswift_client()

    async def require_owned(self, session):
        await conversation_service.lock_rider(session, self.rider_id)
        message = await session.scalar(
            select(Message).where(Message.id == self.claimed.message_id).with_for_update()
        )
        conversation = await session.scalar(
            select(Conversation)
            .where(Conversation.id == self.claimed.conversation_id)
            .with_for_update()
        )
        if (
            message.processing_token != self.claimed.token
            or message.processing_status != "PROCESSING"
            or conversation.rider_id != self.rider_id
            or conversation.handling_mode != "AI"
            or conversation.control_version != self.claimed.control_version
            or conversation.status == "RESOLVED"
            or message.processing_expires_at is None
            or message.processing_expires_at <= datetime.now(UTC)
        ):
            raise OwnershipLost("Conversation execution no longer owned")
        return message, conversation

    def validate(self, request):
        if not isinstance(request, ClaimRequest) or request.rider_id != self.rider_id:
            raise ValueError("Tool identity must match trusted context")
        if (
            len(request.trip_ids) > 20
            or len(set(request.trip_dates + request.penalty_dates + request.incentive_dates)) > 7
        ):
            raise ValueError("Investigation scope exceeds tool limits")

    async def audit(self, name, output, *, event_type="tool_call", input=None):
        async with self.factory() as session, session.begin():
            await self.require_owned(session)
            trace_service.record(
                session,
                self.claimed.conversation_id,
                event_type,
                name,
                input={"message_id": self.claimed.message_id, **(input or {})},
                output=output,
            )

    async def load_context(self):
        async with self.factory() as session:
            message = await session.get(Message, self.claimed.message_id)
            conversation = await session.get(Conversation, self.claimed.conversation_id)
            history = list(
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.is_internal.is_(False),
                        Message.created_at <= message.created_at,
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(12)
                )
            )
            return {
                "text": message.content,
                "received_at": message.received_at,
                "reference_time": datetime.fromisoformat(message.agent_state["reference_time"])
                if (message.agent_state or {}).get("reference_time")
                else message.received_at,
                "context": conversation.context.get("agent", {}),
                "history": [
                    {
                        "sender": m.sender_type,
                        "text": m.content,
                        "received_at": (m.received_at or m.created_at).isoformat(),
                        "reference_time": (m.agent_state or {}).get("reference_time"),
                    }
                    for m in reversed(history)
                ],
                "saved": (message.agent_state or {}).get("extraction"),
            }

    async def checkpoint(self, extraction):
        async with self.factory() as session, session.begin():
            message, conversation = await self.require_owned(session)
            state = dict(message.agent_state or {})
            state["extraction"] = extraction.model_dump(mode="json")
            message.agent_state = state
            context = dict(conversation.context)
            context["agent"] = {**context.get("agent", {}), "extraction": state["extraction"]}
            conversation_service.set_context(conversation, context)
            trace_service.record(
                session,
                conversation.id,
                "decision",
                "intent_extraction",
                input={"message_id": message.id},
                output={**state["extraction"], "prompt_version": PROMPT_VERSION},
            )

    @audited_tool
    async def get_rider_profile(self):
        async with self.factory() as session:
            rider = await session.get(Rider, self.rider_id)
            if rider is None:
                raise ValueError("Trusted rider not found")
            result = {"rider_id": rider.rider_id, "city": rider.city}
        await self.audit("get_rider_profile", {"found": True})
        return result

    @audited_tool
    async def get_rider_trips(self, request):
        from app.realtime.publisher import progress

        await progress(self.claimed, "checking_trip_records")
        self.validate(request)
        days = sorted(set(request.trip_dates + request.penalty_dates + request.incentive_dates))
        async with self.factory() as session:
            rows = await financial.trips_for_scope(session, self.rider_id, request.trip_ids, days)
            if any(t.rider_id != self.rider_id for t in rows):
                await self.audit("get_rider_trips", {"error": "trip_not_owned"})
                raise EvidenceConflict("Trip not found for trusted rider")
            values = [
                {"trip_id": t.trip_id, "status": t.status, "started_at": t.started_at} for t in rows
            ]
        await self.audit("get_rider_trips", {"count": len(values)})
        return values

    @audited_tool
    async def get_payout_history(self, request):
        from app.realtime.publisher import progress

        await progress(self.claimed, "retrieving_payout_history")
        self.validate(request)
        days = sorted(set(request.trip_dates + request.penalty_dates + request.incentive_dates))
        async with self.factory() as session:
            rows = await financial.trips_for_scope(session, self.rider_id, request.trip_ids, days)
            if any(t.rider_id != self.rider_id for t in rows):
                raise EvidenceConflict("Trip not found for trusted rider")
            payouts = await financial.payouts_for_scope(
                session, self.rider_id, [t.trip_id for t in rows], days
            )
            values = [
                {"line_id": p.line_id, "amount": p.amount, "line_type": p.line_type}
                for p in payouts
            ]
        await self.audit("get_payout_history", {"count": len(values)})
        return values

    @audited_tool
    async def reconcile_dispute(self, request):
        from app.realtime.publisher import progress

        await progress(self.claimed, "calculating_verified_shortfall")
        self.validate(request)
        ledger = await self.client.ledger(self.rider_id)
        async with self.factory() as session:
            coverage = await source_coverage(session, request)
            try:
                evidence, _ = await provider_evidence(session, self.rider_id, ledger)
            except EvidenceUnavailable as exc:
                await self.audit(
                    "provider_evidence_unresolved", {"reason": str(exc)}, event_type="decision"
                )
                evidence = PaymentEvidence()
            result = await reconcile(
                session, request, source_data_complete=coverage, evidence=evidence
            )
        await self.audit(
            "reconcile_dispute",
            {
                "rider_id": request.rider_id,
                "received_at": request.received_at,
                "status": result.status,
                "verified_shortfall": result.verified_shortfall,
                "outstanding": result.outstanding,
                "source_coverage": coverage,
                "provider_available": True,
                "items": [
                    {
                        "type": i.source_type,
                        "id": i.source_id,
                        "expected": i.expected_amount,
                        "historical": i.historical_paid,
                        "outstanding": i.outstanding,
                        "reasons": i.reasons,
                    }
                    for i in result.items
                ],
            },
        )
        return result, coverage

    async def ensure_dispute(self, request, result):
        self.validate(request)
        keys = sorted((i.source_type, i.source_id) for i in result.items)
        canonical = {
            "rider_id": self.rider_id,
            "items": keys or request.model_dump(mode="json", exclude={"received_at"}),
        }
        if request.reference_time is not None and request.reference_time != request.received_at:
            # New demo investigations must not rewrite an old, out-of-window dispute.
            # Prior source/payment evidence and real-day reservations still prevent duplicates.
            canonical["demo_reference_time"] = request.reference_time.isoformat()
        scope_key = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        identifier = uuid5(NAMESPACE_URL, "quickdrop:dispute:" + scope_key)
        async with self.factory() as session, session.begin():
            await self.require_owned(session)
            dispute = await session.get(Dispute, identifier)
            if dispute is None:
                dispute = Dispute(
                    id=identifier,
                    rider_id=self.rider_id,
                    conversation_id=self.claimed.conversation_id,
                    status="VERIFIED"
                    if result.eligible and result.verified_shortfall > 0
                    else "INVESTIGATING",
                    verified_amount=result.verified_shortfall if result.eligible else None,
                    details={"scope_key": scope_key, "request": request.model_dump(mode="json")},
                )
                session.add(dispute)
                await session.flush()
                for item in result.items:
                    if (
                        item.expected_amount is not None
                        and item.historical_paid is not None
                        and item.raw_difference is not None
                    ):
                        session.add(
                            DisputeItem(
                                dispute_id=identifier,
                                source_type=item.source_type,
                                source_id=item.source_id,
                                expected_amount=item.expected_amount,
                                actual_amount=item.historical_paid,
                                difference=item.raw_difference,
                            )
                        )
                trace_service.record(
                    session,
                    self.claimed.conversation_id,
                    "decision",
                    "dispute_persisted",
                    input={"message_id": self.claimed.message_id},
                    output={"dispute_id": identifier, "status": dispute.status},
                )
            message, conversation = await self.require_owned(session)
            context = dict(conversation.context)
            agent = dict(context.get("agent", {}))
            agent["dispute_ids"] = list(
                dict.fromkeys(agent.get("dispute_ids", []) + [str(identifier)])
            )[-12:]
            context["agent"] = agent
            conversation_service.set_context(conversation, context)
        return identifier

    async def check_payment_eligibility(self, request, result):
        from app.realtime.publisher import progress

        await progress(self.claimed, "checking_payment_eligibility")
        self.validate(request)
        allowed = (
            result.eligible
            and result.status == "VERIFIED"
            and result.outstanding is not None
            and result.outstanding > 0
        )
        await self.audit(
            "check_payment_eligibility", {"ready_for_authorization": allowed}, event_type="decision"
        )
        return allowed

    @audited_tool
    async def create_payment_intent(self, identifier, request, *, coverage):
        from app.realtime.publisher import progress

        await progress(self.claimed, "authorizing_payment")
        self.validate(request)
        result = await authorize_payment(
            self.factory,
            self.client,
            identifier,
            request,
            source_data_complete=coverage,
            execution_guard=self.require_owned,
        )
        if result.status == "BLOCKED" and result.reason == "Provider history unavailable":
            raise ProviderUnavailable("Authorization ledger unavailable")
        return result

    async def create_ops_escalation(self, identifier, reason):
        from app.realtime.publisher import progress

        await progress(self.claimed, "escalating_to_ops")
        async with self.factory() as session, session.begin():
            await self.require_owned(session)
            dispute = await session.get(Dispute, identifier)
            if dispute is None or dispute.rider_id != self.rider_id:
                raise ValueError("Dispute not owned")
            result = await approval_queue(session, dispute, None, reason, escalation=True)
            trace_service.record(
                session,
                self.claimed.conversation_id,
                "decision",
                "agent_escalation",
                input={"dispute_id": identifier},
                output={"queue_id": result.queue_id, "reason": reason},
            )
            return result

    @audited_tool
    async def payment_status(self, result=None, *, request=None):
        async with self.factory() as session:
            conversation = await session.get(Conversation, self.claimed.conversation_id)
            ids = [
                UUID(value)
                for value in conversation.context.get("agent", {}).get("dispute_ids", [])
            ]
            conditions = [Dispute.rider_id == self.rider_id]
            if request is not None:
                self.validate(request)
                days = sorted(
                    set(request.trip_dates + request.penalty_dates + request.incentive_dates)
                )
                trips = await financial.trips_for_scope(
                    session, self.rider_id, request.trip_ids, days
                )
                own_ids = [trip.trip_id for trip in trips if trip.rider_id == self.rider_id]
                keys = own_ids + [day.isoformat() for day in request.incentive_dates]
                conditions.append(
                    Dispute.id.in_(
                        select(DisputeItem.dispute_id).where(DisputeItem.source_id.in_(keys))
                    )
                )
            elif result is not None and result.items:
                predicates = [
                    and_(
                        DisputeItem.source_type == item.source_type,
                        DisputeItem.source_id == item.source_id,
                    )
                    for item in result.items
                ]
                conditions.append(
                    Dispute.id.in_(select(DisputeItem.dispute_id).where(or_(*predicates)))
                )
            elif ids:
                conditions.append(Dispute.id.in_(ids))
            else:
                # An unscoped question must never pick another claim's latest payment.
                conditions.append(Dispute.conversation_id == self.claimed.conversation_id)
            intents = list(
                await session.scalars(
                    select(PaymentIntent)
                    .join(Dispute, Dispute.id == PaymentIntent.dispute_id)
                    .where(*conditions)
                    .options(selectinload(PaymentIntent.dispute).selectinload(Dispute.items))
                    .order_by(PaymentIntent.created_at.desc(), PaymentIntent.id.desc())
                    .limit(12)
                )
            )
            queues = list(
                await session.scalars(
                    select(OpsQueue)
                    .join(Dispute, Dispute.id == OpsQueue.dispute_id)
                    .where(
                        *conditions,
                        OpsQueue.type == "approval",
                        OpsQueue.status.in_(("PENDING", "IN_REVIEW")),
                        OpsQueue.resolved_at.is_(None),
                    )
                    .order_by(OpsQueue.created_at.desc(), OpsQueue.id.desc())
                    .limit(12)
                )
            )
            ledger = None
            if intents:
                try:
                    ledger = await self.client.ledger(self.rider_id)
                except ProviderUnavailable:
                    pass
            values = []
            for intent in intents:
                check = (
                    match_payout(
                        ledger,
                        rider_id=self.rider_id,
                        reference=reference_for(intent.id),
                        amount=intent.amount,
                        provider_id=intent.provider_payout_id,
                    )
                    if ledger is not None
                    else None
                )
                values.append(
                    {
                        "id": str(intent.id),
                        "amount": str(intent.amount),
                        "status": intent.status,
                        "confirmed": intent.status == "SUCCEEDED"
                        and bool(intent.provider_payout_id),
                        "provider_check": check.kind if check else "UNAVAILABLE",
                        "sources": [item.source_id for item in intent.dispute.items],
                        "expected": str(sum(item.expected_amount for item in intent.dispute.items)),
                        "historical": str(sum(item.actual_amount for item in intent.dispute.items)),
                    }
                )
            values.extend(
                {
                    "id": str(q.id),
                    "amount": str(q.amount),
                    "status": "AWAITING_APPROVAL",
                    "confirmed": False,
                }
                for q in queues
            )
            linked = [str(i.dispute_id) for i in intents] + [str(q.dispute_id) for q in queues]
        if linked:
            async with self.factory() as session, session.begin():
                _, conversation = await self.require_owned(session)
                context = dict(conversation.context)
                agent = dict(context.get("agent", {}))
                agent["dispute_ids"] = list(dict.fromkeys(agent.get("dispute_ids", []) + linked))[
                    -12:
                ]
                context["agent"] = agent
                conversation_service.set_context(conversation, context)
        await self.audit("get_payment_status", {"payments": values})
        return values

    async def technical_escalation(self):
        from app.realtime.publisher import progress

        await progress(self.claimed, "investigation_failed", kind="agent.failed")
        identifier = uuid5(NAMESPACE_URL, "quickdrop:agent-error:" + str(self.claimed.message_id))
        async with self.factory() as session, session.begin():
            await self.require_owned(session)
            dispute = await session.get(Dispute, identifier)
            if dispute is None:
                dispute = Dispute(
                    id=identifier,
                    rider_id=self.rider_id,
                    conversation_id=self.claimed.conversation_id,
                    status="INVESTIGATING",
                    details={"message_id": str(self.claimed.message_id)},
                )
                session.add(dispute)
                await session.flush()
            await approval_queue(
                session,
                dispute,
                None,
                "Automated investigation could not complete; review required",
                escalation=True,
            )
            trace_service.record(
                session,
                self.claimed.conversation_id,
                "error",
                "agent_investigation_exhausted",
                input={"message_id": self.claimed.message_id},
                output={"dispute_id": identifier, "route": "escalation"},
            )
        return "Your concern is queued for support review. No payment outcome is confirmed yet."

    async def mark_clarification(self):
        async with self.factory() as session, session.begin():
            _, conversation = await self.require_owned(session)
            if conversation.status in {"OPEN", "AWAITING_INFORMATION"}:
                conversation.status = "AWAITING_INFORMATION"
