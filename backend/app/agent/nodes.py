"""Graph nodes orchestrate validated tools; no SQL or payment arithmetic here."""

import re
from collections import defaultdict

from app.agent import llm
from app.agent.dates import grounded, resolve_date
from app.agent.replies import TEXT, outcome_reply, status_reply
from app.agent.state import Extraction
from app.repositories.trips import IST
from app.services.financial.types import ClaimRequest


class AgentDeferred(Exception):
    pass


def language_hint(text):
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    return (
        "hinglish"
        if re.search(r"\b(bhai|nahi|mera|paisa|payout.*aaya|tarikh|wala|kal)\b", text, re.I)
        else "en"
    )


def resolve_token(token, state):
    anchor = state["received_at"]
    if not grounded(token, state["text"]):
        for previous in reversed(state["history"]):
            if previous["sender"] == "RIDER" and grounded(token, previous["text"]):
                if previous.get("received_at"):
                    from datetime import datetime

                    anchor = datetime.fromisoformat(previous["received_at"])
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
            grouped[kind]["dates"].add(resolve_token(token, state))
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
        hint = language_hint(state["text"])
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
                    received_at=state["received_at"].astimezone(IST),
                    history=state["history"],
                    context=state["context"],
                )
                extraction = Extraction.model_validate(extraction)
            except llm.ExtractionUnavailable:
                await self.tools.audit(
                    "intent_extraction_failed", {"retryable": True}, event_type="error"
                )
                raise AgentDeferred from None
            await self.tools.checkpoint(extraction)
        if extraction.intent in {"unsafe", "other", "status"}:
            return {"extraction": extraction, "decision": extraction.intent}
        try:
            scope_requests(extraction, state)
        except ValueError as exc:
            await self.tools.mark_clarification()
            await self.tools.audit(
                "clarification_requested", {"missing": str(exc)}, event_type="decision"
            )
            return {"extraction": extraction, "decision": "clarify", "missing": [str(exc)]}
        return {"extraction": extraction}

    async def investigate(self, state):
        outcomes = []
        requests = scope_requests(state["extraction"], state)
        review_requested = state["extraction"].records_disputed or any(
            c.kind == "RECORD_DISPUTE" for c in state["extraction"].claims
        )
        for request in requests:
            try:
                trips = await self.tools.get_rider_trips(request)
                constraints = {
                    resolve_token(token, state)
                    for claim in state["extraction"].claims
                    if set(claim.trip_ids) & set(request.trip_ids)
                    for token in claim.date_tokens
                }
                if constraints and any(
                    trip["trip_id"] in request.trip_ids
                    and trip["started_at"].astimezone(IST).date() not in constraints
                    for trip in trips
                ):
                    raise ValueError("Trip date differs from supplied date")
                await self.tools.get_payout_history(request)
            except ValueError:
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
            if review_requested or result.status in {
                "REQUIRES_REVIEW",
                "NEEDS_INFORMATION",
                "INELIGIBLE",
                "PARTIALLY_ELIGIBLE",
                "NEEDS_RECONCILIATION",
            }:
                identifier = await self.tools.ensure_dispute(request, result)
                await self.tools.create_ops_escalation(
                    identifier, "Source records, eligibility, or provider history need review"
                )
                outcomes.append({"kind": "review"})
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
                    outcomes.append({"kind": "status", "payments": existing})
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
            else:
                await self.tools.create_ops_escalation(
                    identifier, "Payment authorization requires verification"
                )
                kind = "review"
            outcomes.append({"kind": kind, "items": details, "amount": str(result.outstanding)})
        await self.tools.audit(
            "agent_financial_decision", {"outcomes": outcomes}, event_type="decision"
        )
        return {"outcomes": outcomes}

    async def reply(self, state):
        language = state["extraction"].language
        decision = state.get("decision")
        if decision == "status":
            reply = status_reply(await self.tools.payment_status(), language)
        elif decision:
            reply = TEXT[language].get(decision, TEXT[language]["clarify"])
        else:
            reply = outcome_reply(state["outcomes"], language)
        return {"reply": reply}
