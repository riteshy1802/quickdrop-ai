"""Collect minimal snapshots during flush; publish only after the outer commit."""

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.models import Conversation, Dispute, Message, OpsQueue, PaymentIntent
from app.realtime.publisher import Run, current_run, make_event, schedule


@event.listens_for(Session, "before_flush")
def collect(session, *_):
    pending = session.info.setdefault("live_rows", {})
    for row in set(session.new) | set(session.dirty):
        if isinstance(row, (Conversation, Message, Dispute, OpsQueue, PaymentIntent)):
            changes = {
                key
                for key in inspect(row).attrs.keys()
                if inspect(row).attrs[key].history.has_changes()
            }
            pending[id(row)] = (row, row in session.new, changes)


@event.listens_for(Session, "after_flush_postexec")
def snapshot(session, *_):
    events = session.info.setdefault("live_events", [])
    for row, new, changes in session.info.pop("live_rows", {}).values():
        if isinstance(row, Conversation):
            cid, rider = row.id, row.rider_id
            kind, data, internal = (
                "conversation.updated",
                {"status": row.status, "control_version": row.control_version},
                False,
            )
        else:
            if isinstance(row, Message):
                cid = row.conversation_id
            elif isinstance(row, Dispute):
                cid = row.conversation_id
            else:
                cid = session.scalar(
                    select(Dispute.conversation_id).where(Dispute.id == row.dispute_id)
                )
            rider = session.scalar(select(Conversation.rider_id).where(Conversation.id == cid))
            internal = isinstance(row, Message) and row.is_internal
            if isinstance(row, Message):
                kind, data = "message.created", {"message_id": row.id, "sender": row.sender_type}
            elif isinstance(row, Dispute):
                kind, data = "dispute.updated", {"dispute_id": row.id, "status": row.status}
            elif isinstance(row, OpsQueue):
                kind, data = "ops.case.updated", {"case_id": row.id, "status": row.status}
            else:
                kind, data = (
                    "payment.status_changed",
                    {"payment_id": row.id, "dispute_id": row.dispute_id, "status": row.status},
                )
        if isinstance(row, Conversation) and "handling_mode" in changes and not new:
            kind = (
                "conversation.takeover" if row.handling_mode == "HUMAN" else "conversation.handoff"
            )
        if isinstance(row, OpsQueue) and new:
            kind = "ops.case.created"
        if (
            isinstance(row, PaymentIntent)
            and "last_reconciled_at" in changes
            and row.last_reconciled_at
        ):
            events.append((make_event("payment.reconciled", cid, rider, **data), internal))
        if isinstance(row, Message) and not new:
            if row.sender_type == "RIDER" and row.processing_status == "FAILED":
                events.append(
                    (make_event("agent.failed", cid, rider, status="retry_pending"), internal)
                )
            elif row.sender_type == "RIDER" and row.processing_status == "RECEIVED":
                events.append(
                    (
                        make_event("agent.status", cid, rider, status="verification_pending"),
                        internal,
                    )
                )
            continue
        events.append((make_event(kind, cid, rider, **data), internal))
        # Final responses already exist in PostgreSQL before any visible answer is sent.
        if isinstance(row, Message) and row.sender_type == "AI" and not row.is_internal:
            if current_run.get() is None or current_run.get().conversation_id != cid:
                current_run.set(Run(row.id, cid, rider))
            version = session.scalar(
                select(Conversation.control_version).where(Conversation.id == cid)
            )
            # Transport chunks of the committed deterministic answer, never model reasoning.
            for start in range(0, len(row.content), 64):
                events.append(
                    (
                        make_event(
                            "agent.message.delta",
                            cid,
                            rider,
                            message_id=row.id,
                            text=row.content[start : start + 64],
                            control_version=version,
                        ),
                        False,
                    )
                )
            for kind in ("agent.message.completed", "agent.completed"):
                events.append(
                    (
                        make_event(
                            kind,
                            cid,
                            rider,
                            message_id=row.id,
                            text=row.content,
                            control_version=version,
                        ),
                        False,
                    )
                )


@event.listens_for(Session, "after_commit")
def committed(session):
    if not session.in_nested_transaction():
        schedule(session.info.pop("live_events", []))


@event.listens_for(Session, "after_rollback")
def rolled_back(session):
    session.info.pop("live_rows", None)
    session.info.pop("live_events", None)
