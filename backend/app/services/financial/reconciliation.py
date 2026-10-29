"""Read-only investigation. A verified CSV shortfall never authorizes a payment."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import claim_time
from app.data_quality.normalize import prepare_trip
from app.data_quality.report import DataQualityIssue
from app.repositories import financial, riders
from app.repositories.trips import IST
from app.services.financial.calculator import (
    ZERO,
    cancellation_pay,
    completed_trip_pay,
    exact_sum,
    subtract,
)
from app.services.financial.eligibility import (
    date_eligibility,
    trip_eligibility,
)
from app.services.financial.incentive import completed_trip_count, expected_incentive
from app.services.financial.types import (
    ClaimRequest,
    ConfirmedPayment,
    FinancialSnapshot,
    PaymentEvidence,
    PayoutRecord,
    PriorClaim,
    PriorIntent,
    PriorItem,
    ReconciledItem,
    ReconciliationResult,
    SourceKey,
    TripRecord,
)


def _key(source: SourceKey) -> tuple:
    return source.source_type, source.source_id, source.service_date


def _unique(records: Iterable, id_field: str) -> tuple[dict, bool]:
    result = {}
    conflict = False
    for record in records:
        key = getattr(record, id_field)
        if key in result and result[key] != record:
            conflict = True
        result[key] = record
    return result, conflict


def _confirmed(evidence: PaymentEvidence) -> tuple[dict[str, ConfirmedPayment], bool]:
    payments, conflict = _unique(evidence.confirmed, "provider_payout_id")
    intents = {}
    for payment in payments.values():
        if payment.intent_id:
            previous = intents.setdefault(payment.intent_id, payment.provider_payout_id)
            conflict |= previous != payment.provider_payout_id
    return payments, conflict


def _payment_blockers(item, prior_claims, payments):
    claims, intents, reasons = set(), set(), []
    for claim in prior_claims:
        matches = any(
            prior.source_type == item.source_type
            and (
                prior.source_id == item.source_id
                or (item.source_type == "penalty" and prior.source_id in item.historical_line_ids)
            )
            for prior in claim.items
        )
        # Legacy claims without item scope cannot safely be attributed to another dispute.
        unscoped = not claim.items and (claim.intents or claim.status == "RESOLVED")
        if not matches and not unscoped:
            continue
        all_confirmed = bool(claim.intents)
        for intent in claim.intents:
            confirmation = payments.get(intent.provider_payout_id)
            confirmed = (
                intent.status == "SUCCEEDED"
                and confirmation is not None
                and confirmation.amount == intent.amount
                and confirmation.intent_id in (None, intent.id)
                and any(_key(a) == _key(item) for a in confirmation.allocations)
            )
            if not confirmed:
                intents.add(intent.id)
                all_confirmed = False
        if unscoped or (claim.status == "RESOLVED" and not all_confirmed):
            claims.add(claim.id)
    if intents:
        reasons.append(
            "A prior payment is reserved, in flight, uncertain, or lacks provider confirmation"
        )
    if claims:
        reasons.append("A settled or unscoped prior claim requires explicit payment reconciliation")
    return tuple(sorted(claims)), tuple(sorted(intents)), tuple(reasons)


def _apply_payment_evidence(item, prior_claims, evidence, payments, evidence_conflict):
    if not item.eligible or item.raw_difference is None:
        return item
    adjustments = exact_sum(
        allocation.amount
        for payment in payments.values()
        for allocation in payment.allocations
        if _key(allocation) == _key(item)
    )
    claims, intents, reasons = _payment_blockers(item, prior_claims, payments)
    if evidence_conflict:
        reasons += ("Conflicting provider evidence must be resolved",)
    if item.verified_shortfall > ZERO and not evidence.provider_history_complete:
        reasons += ("Provider payment history has not been reconciled for this source",)
    if (
        claims
        or intents
        or evidence_conflict
        or (item.verified_shortfall > ZERO and not evidence.provider_history_complete)
    ):
        return item.model_copy(
            update={
                "confirmed_adjustments": adjustments,
                "outstanding": None,
                "status": "NEEDS_RECONCILIATION",
                "reasons": item.reasons + reasons,
                "blocking_claim_ids": claims,
                "blocking_intent_ids": intents,
            }
        )
    return item.model_copy(
        update={
            "confirmed_adjustments": adjustments,
            "outstanding": max(ZERO, subtract(item.verified_shortfall, adjustments)),
            "reasons": item.reasons
            + (
                ("Confirmed provider adjustments are accounted for this source",)
                if adjustments
                else ()
            ),
        }
    )


def _unavailable(kind, source_id, day, reason, status="NEEDS_INFORMATION"):
    return ReconciledItem(
        source_type=kind,
        source_id=source_id,
        service_date=day,
        eligible=False,
        status=status,
        reasons=(reason,),
    )


def _compare(key, expected, lines, reasons):
    line_ids = tuple(sorted(line.line_id for line in lines))
    # Do not guess whether a wrong-date entry is late pay, a different claim or corruption.
    if any(line.payout_date != key.service_date for line in lines):
        return ReconciledItem(
            **key.model_dump(),
            eligible=False,
            status="NEEDS_INFORMATION",
            expected_amount=expected,
            historical_line_ids=line_ids,
            reasons=reasons + ("Payout date disagrees with the source IST date",),
        )
    if any(
        (key.source_type == "penalty" and line.amount > ZERO)
        or (key.source_type != "penalty" and line.amount < ZERO)
        for line in lines
    ):
        return ReconciledItem(
            **key.model_dump(),
            eligible=False,
            status="NEEDS_INFORMATION",
            expected_amount=expected,
            historical_line_ids=line_ids,
            reasons=reasons + ("Historical line sign requires clarification",),
        )
    paid = exact_sum(line.amount for line in lines)
    difference = subtract(expected, paid)
    shortfall = max(ZERO, difference)
    explanation = (
        "A historical payment shortfall was found"
        if shortfall
        else "Historical pay matches policy"
        if difference == ZERO
        else "Historical records show overpayment; no negative payment is requested"
    )
    if not lines:
        reasons += ("No historical payout line was found in the attested complete source scope",)
    return ReconciledItem(
        **key.model_dump(),
        eligible=True,
        status="VERIFIED" if shortfall else "NO_SHORTFALL",
        expected_amount=expected,
        historical_paid=paid,
        raw_difference=difference,
        verified_shortfall=shortfall,
        historical_line_ids=line_ids,
        reasons=reasons + (explanation,),
    )


def reconcile_records(
    request: ClaimRequest,
    snapshot: FinancialSnapshot,
    evidence: PaymentEvidence | None = None,
) -> ReconciliationResult:
    """Pure reconciliation over trusted records. No DB access, network calls or mutations."""
    evidence = evidence or PaymentEvidence()
    prepared = [prepare_trip(trip) for trip in snapshot.trips]
    quality = {entry.source_id: entry for entry in snapshot.trip_quality}
    for _, entry in prepared:
        quality.setdefault(entry.source_id, entry)
    changes = {
        change.rule_id: change for entry in quality.values() for change in entry.transformations
    }
    trip_map, conflicting_trips = _unique((trip for trip, _ in prepared), "trip_id")
    _, raw_trip_conflict = _unique(snapshot.trips, "trip_id")
    conflicting_trips |= raw_trip_conflict
    payout_map, conflicting_lines = _unique(snapshot.payouts, "line_id")
    lines = tuple(payout_map.values())
    payments, evidence_conflict = _confirmed(evidence)
    if evidence.rider_id is not None and evidence.rider_id != request.rider_id:
        payments = {}
        evidence_conflict = True
    targets = set()
    trip_dates = set(request.trip_dates)
    penalty_dates = set(request.penalty_dates)
    full_ids = set(request.trip_ids)
    full_ids.update(
        t.trip_id
        for t in trip_map.values()
        if t.rider_id == request.rider_id and t.started_at.astimezone(IST).date() in trip_dates
    )
    for trip_id in full_ids:
        trip = trip_map.get(trip_id)
        targets.add(("trip", trip_id))
        if trip and (
            trip.status != "completed"
            or any(p.trip_id == trip_id and p.line_type == "cancellation_penalty" for p in lines)
        ):
            targets.add(("penalty", trip_id))
    for trip in trip_map.values():
        if (
            trip.rider_id == request.rider_id
            and trip.started_at.astimezone(IST).date() in penalty_dates
        ):
            if trip.status == "cancelled_by_rider" or any(
                p.trip_id == trip.trip_id and p.line_type == "cancellation_penalty" for p in lines
            ):
                targets.add(("penalty", trip.trip_id))
    for line in lines:
        if line.line_type == "cancellation_penalty" and line.payout_date in penalty_dates:
            if line.trip_id:
                targets.add(("penalty", line.trip_id))
    items = []
    invalid_snapshot = (
        conflicting_trips
        or conflicting_lines
        or any(line.rider_id != request.rider_id for line in lines)
    )
    for kind, source_id in sorted(targets):
        trip = trip_map.get(source_id)
        eligibility = trip_eligibility(
            request.rider_id, snapshot.rider_exists, trip, claim_time(request)
        )
        if not eligibility.eligible:
            day = (
                trip.started_at.astimezone(IST).date()
                if trip and trip.rider_id == request.rider_id
                else None
            )
            item = _unavailable(kind, source_id, day, "; ".join(eligibility.reasons), "INELIGIBLE")
        elif (
            kind == "trip"
            and trip.status == "completed"
            and quality[source_id].classification == "REQUIRES_REVIEW"
        ):
            item = _unavailable(
                kind,
                source_id,
                trip.started_at.astimezone(IST).date(),
                f"Source distance {trip.distance_km} km exceeds the 100 km data-quality "
                "review threshold; verify units before calculating an adjustment",
                "REQUIRES_REVIEW",
            ).model_copy(
                update={
                    "data_quality": "REQUIRES_REVIEW",
                    "data_quality_issues": quality[source_id].issues,
                }
            )
        elif not snapshot.source_data_complete or invalid_snapshot:
            item = _unavailable(
                kind,
                source_id,
                trip.started_at.astimezone(IST).date(),
                "Source coverage is incomplete or records conflict",
            )
        else:
            day = trip.started_at.astimezone(IST).date()
            key = SourceKey(source_type=kind, source_id=source_id, service_date=day)
            if kind == "trip":
                expected = (
                    completed_trip_pay(trip.distance_km, trip.surge_multiplier)
                    if trip.status == "completed"
                    else ZERO
                )
            else:
                expected = cancellation_pay(trip.status) if trip.status != "completed" else ZERO
            line_type = "trip" if kind == "trip" else "cancellation_penalty"
            matched = [p for p in lines if p.trip_id == source_id and p.line_type == line_type]
            item = _compare(key, expected, matched, eligibility.reasons)
        if invalid_snapshot and item.status == "NEEDS_INFORMATION":
            item = item.model_copy(
                update={
                    "data_quality": "INVALID",
                    "data_quality_issues": (
                        DataQualityIssue(
                            code="CONFLICTING_SOURCE_DATA",
                            source_id=source_id,
                            classification="INVALID",
                            field="source_records",
                            observed_value="conflicting",
                            reason="Source record identities or ownership conflict",
                        ),
                    ),
                }
            )
        elif kind == "trip" and trip and trip.status == "completed" and item.eligible:
            item = item.model_copy(update={"data_quality": quality[source_id].classification})
        items.append(item)
    for day in sorted(set(request.incentive_dates)):
        eligibility = date_eligibility(day, claim_time(request))
        day_records = [
            t
            for t in trip_map.values()
            if t.rider_id == request.rider_id and t.started_at.astimezone(IST).date() == day
        ]
        if not snapshot.rider_exists:
            item = _unavailable(
                "incentive",
                day.isoformat(),
                day,
                "Trusted rider account was not found",
                "INELIGIBLE",
            )
        elif not eligibility.eligible:
            item = _unavailable(
                "incentive", day.isoformat(), day, eligibility.reasons[0], "INELIGIBLE"
            )
        elif not snapshot.source_data_complete or invalid_snapshot or not day_records:
            item = _unavailable(
                "incentive",
                day.isoformat(),
                day,
                "Complete daily trip records are required to verify the incentive",
            )
        else:
            count = completed_trip_count(day_records, request.rider_id, day)
            key = SourceKey(source_type="incentive", source_id=day.isoformat(), service_date=day)
            matched = [
                p for p in lines if p.payout_date == day and p.line_type == "daily_incentive"
            ]
            item = _compare(
                key,
                expected_incentive(count),
                matched,
                eligibility.reasons + (f"{count} completed trips on this IST date",),
            )
        items.append(item)
    for kind, days in [("trip", trip_dates), ("penalty", penalty_dates)]:
        for day in sorted(days):
            if not any(
                t.rider_id == request.rider_id and t.started_at.astimezone(IST).date() == day
                for t in trip_map.values()
            ):
                items.append(
                    _unavailable(
                        kind,
                        day.isoformat(),
                        day,
                        "Supporting trip records for this date were not found",
                    )
                )
    items = [
        _apply_payment_evidence(i, snapshot.prior_claims, evidence, payments, evidence_conflict)
        for i in items
    ]
    items.sort(key=lambda i: (i.service_date or date.min, i.source_type, i.source_id))
    eligible = bool(items) and all(item.eligible for item in items)
    verified = exact_sum(item.verified_shortfall for item in items)
    needs_payment = any(i.status == "NEEDS_RECONCILIATION" for i in items)
    if any(i.status == "REQUIRES_REVIEW" for i in items):
        status = "REQUIRES_REVIEW"
    elif any(i.status == "NEEDS_INFORMATION" for i in items) or not items:
        status = "NEEDS_INFORMATION"
    elif not eligible:
        status = "INELIGIBLE" if not any(i.eligible for i in items) else "PARTIALLY_ELIGIBLE"
    elif needs_payment:
        status = "NEEDS_RECONCILIATION"
    else:
        status = "VERIFIED" if verified else "NO_SHORTFALL"
    outstanding = (
        exact_sum(i.outstanding for i in items)
        if eligible and all(i.outstanding is not None for i in items)
        else None
    )
    valid = [i for i in items if i.eligible]
    return ReconciliationResult(
        rider_id=request.rider_id,
        received_at=request.received_at,
        eligible=eligible,
        status=status,
        items=tuple(items),
        data_quality_transformations=tuple(changes.values()),
        expected_amount=exact_sum(i.expected_amount for i in valid),
        historical_paid=exact_sum(i.historical_paid for i in valid),
        raw_difference=exact_sum(i.raw_difference for i in valid),
        verified_shortfall=verified,
        confirmed_adjustments=exact_sum(i.confirmed_adjustments for i in valid),
        outstanding=outstanding,
        requires_payment_reconciliation=needs_payment,
        reasons=(
            "Each logical source is reconciled separately; unrelated overpayments are not offset",
            "Financial verification does not authorize a payment",
        )
        + (("Provide trip IDs or explicit claim dates",) if not items else ()),
    )


async def reconcile(
    session: AsyncSession,
    request: ClaimRequest,
    *,
    source_data_complete: bool,
    evidence: PaymentEvidence | None = None,
) -> ReconciliationResult:
    """Load a bounded claim scope and reconcile without creating disputes or payments.

    Caller attests source coverage for the requested dates. Provider history remains
    unverified by default; only a trusted provider reconciliation may supply evidence.
    """
    # Read-only means no incidental flush of caller-owned pending writes either.
    with session.no_autoflush:
        rider = await riders.get_by_id(session, request.rider_id)
        days = sorted(set(request.trip_dates + request.penalty_dates + request.incentive_dates))
        records = await financial.trips_for_scope(session, request.rider_id, request.trip_ids, days)
        own_ids = [t.trip_id for t in records if t.rider_id == request.rider_id]
        payouts = await financial.payouts_for_scope(session, request.rider_id, own_ids, days)
        claims = await financial.prior_claims(session, request.rider_id)
        prepared = [prepare_trip(TripRecord.model_validate(t)) for t in records]
        snapshot = FinancialSnapshot(
            rider_exists=rider is not None,
            source_data_complete=source_data_complete,
            trips=tuple(trip for trip, _ in prepared),
            trip_quality=tuple(entry for _, entry in prepared),
            payouts=tuple(PayoutRecord.model_validate(p) for p in payouts),
            prior_claims=tuple(
                PriorClaim(
                    id=c.id,
                    status=c.status,
                    items=tuple(
                        PriorItem(source_type=i.source_type, source_id=i.source_id) for i in c.items
                    ),
                    intents=tuple(
                        PriorIntent(
                            id=p.id,
                            status=p.status,
                            amount=p.amount,
                            provider_payout_id=p.provider_payout_id,
                        )
                        for p in c.payment_intents
                    ),
                )
                for c in claims
            ),
        )
    return reconcile_records(request, snapshot, evidence)
