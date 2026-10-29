"""Graph nodes orchestrate validated tools; no SQL or payment arithmetic here."""

import re
from collections import defaultdict

from app.agent import llm
from app.agent.dates import grounded, literal_dates, matches_trip_date, resolve_date
from app.agent.education import educational_reply
from app.agent.replies import TEXT, outcome_reply, status_reply
from app.agent.state import Extraction
from app.agent.tools.investigation import EvidenceConflict
from app.agent.understanding import question_focus, repair, response_language
from app.core.clock import claim_time
from app.repositories.trips import IST
from app.services.financial.eligibility import date_eligibility
from app.services.financial.types import ClaimRequest
from app.services.payment_authorization import AUTO_PAY_LIMIT


class AgentDeferred(Exception):
    pass


class ScopeIssue(ValueError):
    def __init__(self, code, value):
        self.code, self.value = code, value
        super().__init__(code)


def language_hint(text):
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    return (
        "hinglish"
        if re.search(
            r"\b(bhai|nahi|nahin|nai|mera|mere|meri|mujhe|aap|aapka|ka|ki|ko|hai|hain|hua|ho|"
            r"kya|kyun|kyu|karo|batao|paise|paisa|tarikh|wala|kal|mein|mei|kab|mila|mili|"
            r"raha|rahi|rahe|karna|galat|kata|kitna|kitne|kitni|namaste|maine|mene|lekin|toh|diya|krdiya|"
            r"samjhao|samajh|samjha|samajhao|kaise|dhanyavaad|shukriya|aasaan|asaan|theek|acha|achha)\b",
            text,
            re.I,
        )
        else "en"
    )


def resolve_token(token, state):
    anchor = state.get("reference_time", state["received_at"])
    if not grounded(token, state["text"]):
        for previous in reversed(state["history"]):
            if previous["sender"] == "RIDER" and grounded(token, previous["text"]):
                if previous.get("received_at"):
                    from datetime import datetime

                    anchor = datetime.fromisoformat(
                        previous.get("reference_time") or previous["received_at"]
                    )
                break
    return resolve_date(token, anchor)


def scope_requests(extraction, state):
    # Merge all fare complaints, so model output cannot split a large claim into small payments.
    grouped = defaultdict(lambda: {"ids": set(), "dates": set()})
    own_text = (
        "\n".join(m["text"] for m in state["history"] if m["sender"] == "RIDER")
        + "\n"
        + state["text"]
    )
    for claim in extraction.claims:
        kind = "PAYOUT" if claim.kind in {"SURGE", "PAYOUT", "RECORD_DISPUTE"} else claim.kind
        for trip_id in claim.trip_ids:
            if not re.fullmatch(r"T\d+", trip_id, re.I) or not grounded(trip_id, own_text):
                raise ValueError("Trip identifiers must be grounded in rider messages")
            grouped[kind]["ids"].add(trip_id.upper())
        for token in claim.date_tokens:
            if not grounded(token, own_text):
                raise ValueError("Dates must be grounded in rider messages")
            try:
                grouped[kind]["dates"].add(resolve_token(token, state))
            except ValueError:
                raise ScopeIssue("invalid_date", token) from None
        if not claim.trip_ids and not claim.date_tokens:
            grouped[kind]  # preserve the missing-scope clarification
    requests = []
    for kind, group in grouped.items():
        if not group["ids"] and not group["dates"]:
            raise ValueError("Trip ID or date is required")
        if kind == "INCENTIVE" and not group["dates"]:
            raise ValueError("Incentive date is required")
        if len(group["ids"]) > 20 or len(group["dates"]) > 7:
            raise ValueError("Limit investigation to 20 trips and seven explicit dates")
        days = tuple(sorted(group["dates"]))
        ids = tuple(sorted(group["ids"]))
        requests.append(
            ClaimRequest(
                rider_id=state["rider_id"],
                received_at=state["received_at"],
                reference_time=state.get("reference_time"),
                trip_ids=ids,
                trip_dates=days if kind == "PAYOUT" and not ids else (),
                penalty_dates=days if kind == "PENALTY" else (),
                incentive_dates=days if kind == "INCENTIVE" else (),
            )
        )
    if not requests:
        raise ValueError("Complaint scope is required")
    return requests


class Nodes:
    def __init__(self, tools, extractor=None):
        self.tools = tools
        self.extractor = extractor or llm.extract

    async def load_context(self, state):
        loaded = await self.tools.load_context()
        await self.tools.get_rider_profile()
        return loaded

    async def understand(self, state):
        from app.realtime.publisher import progress

        await progress(self.tools.claimed, "understanding_complaint")
        hint = response_language(state["text"], language_hint(state["text"]), state["context"])
        other_riders = {value.upper() for value in re.findall(r"\bR\d+\b", state["text"], re.I)} - {
            state["rider_id"].upper()
        }
        injection = re.search(
            r"ignore.{0,30}(rules|instructions|previous)|\bSYSTEM\s*:|approve.{0,20}(all|saare)|reveal.{0,20}(prompt|secret)",
            state["text"],
            re.I,
        )
        if other_riders or injection:
            await self.tools.audit(
                "input_policy_rejected",
                {"identity_or_policy_override": True},
                event_type="decision",
            )
            return {"extraction": Extraction(intent="unsafe", language=hint), "decision": "unsafe"}
        if state.get("saved"):
            extraction = Extraction.model_validate(state["saved"])
        else:
            try:
                extraction = await self.extractor(
                    text=state["text"],
                    received_at=state.get("reference_time", state["received_at"]).astimezone(IST),
                    history=state["history"],
                    context=state["context"],
                )
                extraction = Extraction.model_validate(extraction)
            except llm.ExtractionUnavailable:
                await self.tools.audit(
                    "intent_extraction_failed", {"retryable": True}, event_type="error"
                )
                raise AgentDeferred from None
        extraction = repair(extraction, state)
        # A model classification cannot skip tools for an explicit fare complaint.
        ids = re.findall(r"\bT\d+\b", state["text"], re.I)
        fare_issue = re.search(
            r"\b(surge|payout|fare|payment|paisa|paise)\b.{0,60}\b(missing|short|wrong|nahi|nai|kam)\b"
            r"|\b(missing|short|wrong)\b.{0,60}\b(surge|payout|fare|payment)\b",
            state["text"],
            re.I,
        )
        dates = literal_dates(state["text"])
        if (ids or dates) and fare_issue and extraction.intent in {"other", "status", "help"}:
            ids = list(dict.fromkeys(value.upper() for value in ids))
            if len(ids) > 20 or len(dates) > 7:
                await self.tools.mark_clarification()
                return {"extraction": extraction, "decision": "clarify"}
            extraction = extraction.model_copy(
                update={
                    "intent": "complaint",
                    "claims": extraction.claims
                    or Extraction(
                        intent="complaint",
                        language=hint,
                        claims=[{"kind": "PAYOUT", "trip_ids": ids, "date_tokens": dates}],
                    ).claims,
                }
            )
            await self.tools.audit(
                "investigation_required",
                {"reason": "Explicit scoped fare complaint"},
                event_type="decision",
            )
        # A same-case follow-up reads current status; it is not a new authorization.
        if (
            question_focus(state["text"]) != "status"
            and not ids
            and not dates
            and extraction.intent != "unsafe"
            and not extraction.records_disputed
            and not any(claim.kind == "RECORD_DISPUTE" for claim in extraction.claims)
        ):
            extraction = extraction.model_copy(update={"intent": "status", "claims": []})
        # Script and current rider wording determine the response language, not a model guess.
        extraction = extraction.model_copy(update={"language": hint})
        if extraction.model_dump(mode="json") != state.get("saved"):
            await self.tools.checkpoint(extraction)
        if extraction.intent in {"unsafe", "other", "status", "help"}:
            return {"extraction": extraction, "decision": extraction.intent}
        try:
            scope_requests(extraction, state)
        except ValueError as exc:
            await self.tools.mark_clarification()
            await self.tools.audit(
                "clarification_requested", {"missing": str(exc)}, event_type="decision"
            )
            if isinstance(exc, ScopeIssue):
                return {
                    "extraction": extraction,
                    "outcomes": [{"kind": exc.code, "value": exc.value}],
                    "decision": "invalid_scope",
                }
            return {"extraction": extraction, "decision": "clarify", "missing": [str(exc)]}
        return {"extraction": extraction}

    async def investigate(self, state):
        outcomes = []
        requests = scope_requests(state["extraction"], state)
        review_requested = state["extraction"].records_disputed or any(
            c.kind == "RECORD_DISPUTE" for c in state["extraction"].claims
        )
        for request in requests:
            trips = []
            try:
                trips = await self.tools.get_rider_trips(request)
                missing_ids = set(request.trip_ids) - {trip["trip_id"] for trip in trips}
                if missing_ids:
                    outcomes.append(
                        {"kind": "invalid_trip", "value": ", ".join(sorted(missing_ids))}
                    )
                    await self.tools.mark_clarification()
                    continue
                for claim in state["extraction"].claims:
                    for trip in trips:
                        if trip["trip_id"] not in {value.upper() for value in claim.trip_ids}:
                            continue
                        day = trip["started_at"].astimezone(IST).date()
                        if claim.date_tokens and not any(
                            matches_trip_date(token, day, resolve_token(token, state))
                            for token in claim.date_tokens
                        ):
                            raise EvidenceConflict("Trip date differs from supplied date")
                await self.tools.get_payout_history(request)
            except EvidenceConflict as exc:
                await self.tools.audit(
                    "evidence_conflict", {"reason": str(exc)}, event_type="decision"
                )
                if not review_requested:
                    await self.tools.mark_clarification()
                    outcomes.append(
                        {
                            "kind": "unmatched_trip",
                            "dates": sorted(
                                {
                                    trip["started_at"].astimezone(IST).date().isoformat()
                                    for trip in trips
                                }
                            ),
                        }
                    )
                    continue
                # Persist an ownership-review item without revealing the foreign record.
                result, _ = await self.tools.reconcile_dispute(request)
                identifier = await self.tools.ensure_dispute(request, result)
                await self.tools.create_ops_escalation(
                    identifier, "Trip ownership or supplied dates could not be verified"
                )
                outcomes.append({"kind": "review"})
                continue
            result, coverage = await self.tools.reconcile_dispute(request)
            existing = await self.tools.payment_status(result)
            if existing and result.status == "NEEDS_RECONCILIATION":
                outcomes.append({"kind": "status", "payments": existing})
                continue
            missing_records = result.status == "NEEDS_INFORMATION" or (
                result.status == "INELIGIBLE"
                and all(item.service_date is None for item in result.items)
            )
            if missing_records and not review_requested:
                await self.tools.mark_clarification()
                await self.tools.audit(
                    "clarification_requested",
                    {"missing": "Supporting trip records or claim scope"},
                    event_type="decision",
                )
                outcomes.append({"kind": "no_records"})
                continue
            if review_requested or result.status in {
                "REQUIRES_REVIEW",
                "NEEDS_INFORMATION",
                "INELIGIBLE",
                "PARTIALLY_ELIGIBLE",
                "NEEDS_RECONCILIATION",
            }:
                identifier = await self.tools.ensure_dispute(request, result)
                outside_window = any(
                    item.service_date is not None
                    and not date_eligibility(item.service_date, claim_time(request)).eligible
                    for item in result.items
                )
                await self.tools.create_ops_escalation(
                    identifier,
                    "Claim is outside the seven-day eligibility window"
                    if outside_window
                    else "Source records, eligibility, or provider history need review",
                )
                outcomes.append(
                    {
                        "kind": "review",
                        "reason": "outside_window" if outside_window else result.status,
                    }
                )
                continue
            details = [
                {
                    "source": item.source_id,
                    "expected": str(item.expected_amount)
                    if item.expected_amount is not None
                    else None,
                    "historical": str(item.historical_paid)
                    if item.historical_paid is not None
                    else None,
                }
                for item in result.items
                if item.verified_shortfall > 0 or len(result.items) <= 3
            ]
            if result.outstanding == 0:
                if existing:
                    outcomes.append({"kind": "status", "payments": existing, "duplicate": True})
                else:
                    outcomes.append(
                        {
                            "kind": "no_shortfall",
                            "items": details,
                            "reasons": [
                                reason
                                for item in result.items
                                for reason in item.reasons
                                if "completed trips" in reason
                            ],
                        }
                    )
                continue
            if not await self.tools.check_payment_eligibility(request, result):
                outcomes.append({"kind": "review"})
                continue
            identifier = await self.tools.ensure_dispute(request, result)
            authorization = await self.tools.create_payment_intent(
                identifier, request, coverage=coverage
            )
            if authorization.status == "AUTHORIZED":
                kind = "authorized"
            elif authorization.status == "APPROVAL_REQUIRED":
                kind = "approval"
            elif authorization.status == "EXISTING":
                outcomes.append(
                    {"kind": "status", "payments": await self.tools.payment_status(result)}
                )
                continue
            elif authorization.status == "ESCALATED":
                kind = "review"
            else:
                await self.tools.create_ops_escalation(
                    identifier, "Payment authorization requires verification"
                )
                kind = "review"
            outcomes.append(
                {
                    "kind": kind,
                    "items": details,
                    "amount": str(result.outstanding),
                    "expected": str(result.expected_amount),
                    "historical": str(result.historical_paid),
                    "claim_types": sorted({item.source_type for item in result.items}),
                    "over_auto_limit": result.verified_shortfall > AUTO_PAY_LIMIT,
                    "approval_reason": authorization.reason,
                    "dates": sorted(
                        {
                            item.service_date.isoformat()
                            for item in result.items
                            if item.service_date
                        }
                    ),
                }
            )
        await self.tools.audit(
            "agent_financial_decision", {"outcomes": outcomes}, event_type="decision"
        )
        return {"outcomes": outcomes}

    async def reply(self, state):
        from app.realtime.publisher import progress

        await progress(self.tools.claimed, "preparing_response")
        language = state["extraction"].language
        decision = state.get("decision")
        focus = question_focus(state["text"])
        if decision == "help":
            reply = educational_reply(state)
        elif decision == "status":
            payments = []
            if state["extraction"].claims:
                try:
                    requests = scope_requests(state["extraction"], state)
                except ValueError:
                    requests = []
                for request in requests:
                    payments.extend(await self.tools.payment_status(request=request))
            else:
                payments = await self.tools.payment_status()
            payments = list({item["id"]: item for item in payments}.values())
            direct = bool(re.search(r"matlab|ho chuka|paid|done|मतलब|हो गया", state["text"], re.I))
            reply = status_reply(payments, language, direct=direct, focus=focus)
        elif decision == "invalid_scope":
            reply = outcome_reply(state["outcomes"], language, focus=focus)
        elif decision:
            reply = TEXT[language].get(decision, TEXT[language]["clarify"])
        else:
            reply = outcome_reply(state["outcomes"], language, focus=focus)
        return {"reply": reply}
