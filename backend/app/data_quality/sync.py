"""Controlled synchronization: insert original sources, update approved trip distance only."""

from collections import defaultdict

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.normalize import NormalizationBundle
from app.data_quality.rules import NormalizationError, approved_trip_fingerprint
from app.models import (
    AgentTrace,
    Conversation,
    Dispute,
    DisputeItem,
    Message,
    OpsQueue,
    PaymentIntent,
    PayoutLine,
    Rider,
    Trip,
)

TABLES = [
    (Rider, "riders", "rider_id"),
    (Trip, "trips", "trip_id"),
    (PayoutLine, "payout_lines", "line_id"),
]
HISTORY = [Conversation, Message, Dispute, DisputeItem, PaymentIntent, OpsQueue, AgentTrace]


async def _history_conflicts(session, affected):
    """Conservative: any decision history for an affected rider blocks a basis update.

    Item and JSON formats are not yet standardized across all future writers. A
    rider-level check also catches unscoped decisions, notes and provider UNKNOWNs.
    """
    owners = {row["rider_id"] for row in affected}
    conflicts = []
    if not owners:
        return conflicts
    conversations = list(
        await session.execute(
            select(Conversation.id, Conversation.rider_id).where(Conversation.rider_id.in_(owners))
        )
    )
    by_conversation = {c.id: c.rider_id for c in conversations}
    disputes = list(
        await session.execute(
            select(Dispute.id, Dispute.rider_id, Dispute.status).where(Dispute.rider_id.in_(owners))
        )
    )
    for dispute in disputes:
        conflicts.append(
            dict(
                code="EXISTING_DISPUTE_BASIS",
                rider_id=dispute.rider_id,
                dispute_id=str(dispute.id),
                status=dispute.status,
            )
        )
    intents = list(
        await session.execute(
            select(PaymentIntent.id, PaymentIntent.rider_id, PaymentIntent.status).where(
                PaymentIntent.rider_id.in_(owners)
            )
        )
    )
    for intent in intents:
        conflicts.append(
            dict(
                code="EXISTING_PAYMENT_HISTORY",
                rider_id=intent.rider_id,
                payment_intent_id=str(intent.id),
                status=intent.status,
            )
        )
    if by_conversation:
        traces = list(
            await session.execute(
                select(AgentTrace.id, AgentTrace.conversation_id).where(
                    AgentTrace.conversation_id.in_(by_conversation)
                )
            )
        )
        for trace in traces:
            conflicts.append(
                dict(
                    code="EXISTING_AUDIT_HISTORY",
                    trace_id=str(trace.id),
                    rider_id=by_conversation[trace.conversation_id],
                )
            )
        messages = await session.execute(
            select(Message.id, Message.conversation_id).where(
                Message.conversation_id.in_(by_conversation)
            )
        )
        for message in messages:
            conflicts.append(
                dict(
                    code="EXISTING_MESSAGE_HISTORY",
                    message_id=str(message.id),
                    rider_id=by_conversation[message.conversation_id],
                )
            )
        # Context may contain an earlier financial calculation without a DisputeItem yet.
        contexts = await session.execute(
            select(Conversation.id, Conversation.rider_id).where(
                Conversation.id.in_(by_conversation),
                Conversation.context != {},
            )
        )
        for context in contexts:
            conflicts.append(
                dict(
                    code="EXISTING_CONVERSATION_CONTEXT",
                    conversation_id=str(context.id),
                    rider_id=context.rider_id,
                )
            )
    return conflicts


async def synchronize(
    session: AsyncSession, bundle: NormalizationBundle, *, apply: bool = False
) -> dict:
    """Caller owns one transaction. Any conflict blocks every mutation.

    Apply takes maintenance locks before inspecting data/history, so a payment
    cannot appear between the history check and the approved distance update.
    """
    if session.new or session.dirty or session.deleted:
        raise NormalizationError("Synchronization requires a clean session without pending writes")
    if apply:
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(
            text("LOCK TABLE riders, trips, payout_lines IN SHARE ROW EXCLUSIVE MODE")
        )
        await session.execute(
            text(
                "LOCK TABLE conversations, messages, disputes, dispute_items, "
                "payment_intents, ops_queue, agent_traces IN SHARE MODE"
            )
        )
    target = dict(
        (
            await session.execute(
                text(
                    "SELECT current_database() AS database, current_user AS role, "
                    "inet_server_addr()::text AS server, inet_server_port() AS port"
                )
            )
        )
        .mappings()
        .one()
    )
    plan = {
        "mode": "apply" if apply else "dry-run",
        "status": "planned",
        "target": target,
        "database_counts_before": {},
        "operations": {},
        "conflicts": [],
        "approved_updates": [],
        "history_counts_before": {},
        "applied": {"inserted": 0, "updated": 0},
    }
    pending = defaultdict(list)
    for model, table, key in TABLES:
        plan["database_counts_before"][table] = await session.scalar(
            select(func.count()).select_from(model)
        )
        source = bundle.rows[table]
        ids = [r[key] for r in source]
        existing = {
            r[key]: dict(r)
            for r in (
                await session.execute(select(model.__table__).where(getattr(model, key).in_(ids)))
            ).mappings()
        }
        stats = {"insert": 0, "update": 0, "skip": 0, "conflict": 0}
        for row in source:
            old = existing.get(row[key])
            if old is None:
                pending[table].append(row)
                stats["insert"] += 1
                continue
            changed = [field for field, value in row.items() if old[field] != value]
            if not changed:
                stats["skip"] += 1
            elif (
                table == "trips"
                and changed == ["distance_km"]
                and approved_trip_fingerprint(old)
                and old["distance_km"] == 5000
                and row["distance_km"] == 5
            ):
                plan["approved_updates"].append(
                    dict(
                        source_id=row[key],
                        rider_id=row["rider_id"],
                        field="distance_km",
                        original_value="5000",
                        normalized_value="5",
                        rule_id="T312538_VERIFIED_METRES_TO_KM_V1",
                    )
                )
                stats["update"] += 1
            else:
                stats["conflict"] += 1
                plan["conflicts"].append(
                    dict(
                        code="UNAPPROVED_DATABASE_DIFFERENCE",
                        table=table,
                        source_id=row[key],
                        fields=changed,
                        limitation="Existing source IDs, rider relationships and payout history "
                        "are immutable; "
                        "the only approved UPDATE is the exact trip distance correction",
                    )
                )
        plan["operations"][table] = stats
    for model in HISTORY:
        plan["history_counts_before"][model.__tablename__] = await session.scalar(
            select(func.count()).select_from(model)
        )
    affected = plan["approved_updates"] + pending["trips"] + pending["payout_lines"]
    plan["conflicts"].extend(await _history_conflicts(session, affected))
    plan["source_classifications"] = bundle.report["classification_counts"]
    plan["unresolved_distances_stored_raw"] = len(bundle.report["records_requiring_review"])
    if plan["conflicts"]:
        plan["status"] = "blocked"
        return plan
    if not apply:
        return plan
    for model, table, _ in TABLES:
        for offset in range(0, len(pending[table]), 500):
            await session.execute(insert(model.__table__), pending[table][offset : offset + 500])
            plan["applied"]["inserted"] += len(pending[table][offset : offset + 500])
    for correction in plan["approved_updates"]:
        statement = (
            update(Trip.__table__)
            .where(
                Trip.trip_id == correction["source_id"],
                Trip.rider_id == correction["rider_id"],
                Trip.distance_km == 5000,
            )
            .values(distance_km=5)
        )
        result = await session.execute(statement)
        if result.rowcount != 1:
            raise NormalizationError(
                "Approved trip changed during synchronization; transaction must roll back"
            )
        plan["applied"]["updated"] += 1
    plan["status"] = "applied_in_transaction"
    return plan
