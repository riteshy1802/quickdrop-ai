"""Grounded scope repair; rejected facts never become durable claim authority."""

import re

from app.agent.dates import grounded, literal_dates, resolve_date
from app.agent.state import Complaint


def repair(extraction, state):
    if extraction.intent == "help" and extraction.simplify and extraction.help_topic == "general":
        topic = state["context"].get("extraction", {}).get("help_topic", "general")
        extraction = extraction.model_copy(update={"help_topic": topic})
    text = state["text"]
    anchor = state.get("reference_time", state["received_at"])
    ids = list(dict.fromkeys(value.upper() for value in re.findall(r"\bT\d+\b", text, re.I)))
    dates = literal_dates(text)
    previous = state["context"].get("extraction", {}).get("claims", [])
    explicit_scope = bool(ids or dates)
    date_scope = bool(
        dates
        and not ids
        and not re.search(r"\b(us|ussi|usi|same|that|this)\s+(trip|order)\b", text, re.I)
        and re.search(
            r"\b(orders?|trips?|payout|paisa|paise|payments?)\b|ऑर्डर|ट्रिप|पैसे|भुगतान", text, re.I
        )
    )
    corrected = []
    for claim in extraction.claims:
        tokens = []
        for token in claim.date_tokens:
            try:
                resolve_date(token, anchor)
            except ValueError:
                if grounded(token, text):
                    tokens.append(token)  # Current invalid input needs an explicit explanation.
                continue  # Never resurrect a rejected date from history.
            tokens.append(token)
        if dates and (extraction.correction or (explicit_scope and not ids)):
            tokens = [token for token in tokens if grounded(token, text)]
        # A new day-wide payout complaint must not inherit one old trip selector.
        claim_ids = [] if date_scope else claim.trip_ids
        current = any(grounded(value, text) for value in claim_ids + tokens)
        if explicit_scope and not current:
            continue
        if claim.date_tokens and not tokens and not claim_ids:
            continue
        corrected.append(claim.model_copy(update={"trip_ids": claim_ids, "date_tokens": tokens}))
    if explicit_scope and not corrected:
        # Resolve a supplied ID/date as the answer to a pending question, rather than
        # asking for the same ID/date again. Claim kind is still an untrusted label.
        kinds = {claim.kind for claim in extraction.claims} or {claim["kind"] for claim in previous}
        if len(kinds) == 1 and len(ids) <= 20 and len(dates) <= 7:
            corrected = [Complaint(kind=kinds.pop(), trip_ids=ids, date_tokens=dates)]
    if corrected:
        intent = extraction.intent
        if intent == "other" and previous and explicit_scope:
            intent = "followup"
        return extraction.model_copy(update={"claims": corrected, "intent": intent})
    return extraction.model_copy(update={"claims": corrected})


def response_language(text, hint, context):
    if hint != "en":
        return hint
    remainder = re.sub(r"\bT\d+\b", "", text, flags=re.I)
    for token in literal_dates(text):
        remainder = remainder.replace(token, "")
    if not re.search(r"[a-zA-Z\u0900-\u097f]", remainder):
        return context.get("language", context.get("extraction", {}).get("language", "en"))
    return "en"


def question_focus(text):
    """Recognize follow-up questions without granting financial authority."""
    if re.search(
        r"\b(duplicate|another|again|dobara|phir se)\b|"
        r"\b(aur ek|ek aur)\b.{0,35}\b(adjustment|request|payment|payout)\b|"
        r"दोबारा|दुबारा|एक और",
        text,
        re.I,
    ):
        return "duplicate"
    if re.search(r"\b(kab|when|eta)\b|how long|kitna (?:time|waqt)|कब|कितना समय", text, re.I):
        return "timing"
    return "status"
