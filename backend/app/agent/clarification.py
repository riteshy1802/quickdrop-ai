"""Contextual clarification prose; it has no authority to investigate or move money."""

import re

from app.agent.replies import TEXT


def pending_details(state):
    pending = state["context"].get("pending_clarification")
    if pending:
        return pending
    # Older conversations have the question/history but predate the explicit marker.
    previous = next((m["text"] for m in reversed(state["history"]) if m["sender"] == "AI"), "")
    if previous in {entry["clarify"] for entry in TEXT.values()}:
        return {"missing": ["Trip ID or date is required"]}
    return None


def lacks_details(text):
    return bool(
        re.search(
            r"\b(?:don'?t|do not|cannot|can'?t)\s+(?:have|know|remember|find)\b|"
            r"\b(?:no|without)\s+(?:details|date|trip id)\b|"
            r"\b(?:nahi|nai|nahin)\s+(?:hai|hain|pata|yaad)\b|"
            r"\b(?:pata|yaad)\s+(?:nahi|nai|nahin)\b|"
            r"\b(?:hai|hain)\s+(?:hi\s+)?(?:nai|nahi|nahin)\b|"
            r"(?:नहीं|नही).*(?:है|पता|याद)|(?:पता|याद).*(?:नहीं|नही)",
            text,
            re.I,
        )
    )


def safe_draft(text):
    # Prose may acknowledge or ask. Financial outcomes always use verified renderers.
    forbidden = (
        r"[\d₹०-९]|\b(?:R\d+|T\d+|paid|pay(?:ment)?|refund|credited|approv\w*|authoriz\w*|"
        r"processed|resolved|escalat\w*|queued|transferred|sent|guarantee\w*|support|ops|team|review|"
        r"rupees|rs|money|cash|paisa|paise|wapas|done|completed|initiated|confirmed|checked|"
        r"records?|bhej\w*|manzoor\w*|pushti|otp|password|token)\b|"
        r"भुगतान|भेज|रिफंड|पुष्ट|स्वीकृत|रुपये|रिकॉर्ड|पासवर्ड|ओटीपी|पैसे|मंजूर|सहायता|टीम|"
        r"(?:check|verify)\s+(?:kar\s+diya|kiya|kiye|ho\s+gaya)|https?://"
    )
    return bool(text.strip()) and not re.search(forbidden, text, re.I)


def clarification_reply(state):
    extraction = state["extraction"]
    language = extraction.language
    history = [m["text"] for m in state["history"] if m["sender"] == "AI"]
    unavailable = extraction.details_unavailable
    draft = extraction.clarification_answer.strip()
    if safe_draft(draft) and not any(draft in old for old in history[-4:]):
        acknowledgement = draft
    elif unavailable:
        options = {
            "en": (
                (
                    "I understand—you don't have those details. Do you remember roughly which "
                    "day the deduction happened?"
                ),
                (
                    "I hear you: you don't have the details right now. You can return when "
                    "you find the day or order ID; I won't guess which deduction you mean."
                ),
            ),
            "hinglish": (
                (
                    "Samajh gaya, aapke paas abhi details nahi hain. Kya lagbhag yaad hai kis "
                    "din deduction hua tha?"
                ),
                (
                    "Haan, aapne bataya ki details nahi hain. Jab din ya order ID mil jaaye, "
                    "yahin bata dena; bina pehchaan ke main kisi deduction ka andaaza nahi "
                    "lagaunga."
                ),
            ),
            "hi": (
                ("समझ गया, अभी आपके पास जानकारी नहीं है। क्या लगभग याद है कि कटौती किस दिन हुई थी?"),
                (
                    "हाँ, आपने बताया कि जानकारी नहीं है। तारीख या ऑर्डर आईडी मिल जाए तो इसी "
                    "बातचीत में बता दीजिए; मैं कटौती का अनुमान नहीं लगाऊँगा।"
                ),
            ),
        }[language]
        acknowledgement = next(
            (value for value in options if not any(value in old for old in history[-4:])),
            options[0] if history and options[-1] in history[-1] else options[-1],
        )
    elif not history or not pending_details(state):
        return TEXT[language]["clarify"]
    else:
        acknowledgement = {
            "en": (
                "I still need a way to identify the issue. If the trip ID isn't "
                "available, which day was it?"
            ),
            "hinglish": (
                "Sahi issue pehchaanne ke liye ek detail chahiye. Trip ID nahi hai toh "
                "kis din ki baat hai, woh bata sakte hain?"
            ),
            "hi": (
                "सही समस्या पहचानने के लिए एक जानकारी चाहिए। ट्रिप आईडी नहीं है तो क्या दिन बता सकते हैं?"
            ),
        }[language]
    limitation = {
        "en": (
            "Without a date or order ID, I cannot verify this issue or promise "
            "that money will be returned."
        ),
        "hinglish": (
            "Date ya order ID ke bina main sahi issue ki jaanch nahi kar sakta, "
            "isliye abhi paise lautane ka vaada nahi kar sakta."
        ),
        "hi": (
            "तारीख या ऑर्डर आईडी के बिना सही समस्या की जाँच नहीं कर सकता, "
            "इसलिए अभी पैसे लौटाने का वादा नहीं कर सकता।"
        ),
    }[language]
    return acknowledgement + " " + limitation
