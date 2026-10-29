"""Render only deterministic outcomes. The LLM never writes financial statements."""

TEXT = {
    "en": {
        "clarify": "Which trip or date has the payout issue? Please share the trip ID or date.",
        "unsafe": "I can only help with this account using verified trip and payout records.",
        "other": "I can help with trip payouts, surge, incentives, or cancellation deductions.",
        "review": "This needs support review. No additional payment has been authorized.",
        "empty_status": "No payment is confirmed for this conversation yet.",
    },
    "hinglish": {
        "clarify": "Kaunse din ya trip ka payout galat laga? Date ya trip ID bata dijiye.",
        "unsafe": (
            "Main sirf is account ke verified trip aur payout records par madad kar sakta hoon."
        ),
        "other": "Trip payout, surge, incentive ya cancellation penalty ki details bata dijiye.",
        "review": (
            "Yeh support review ke liye bheja hai. Koi additional payment authorize nahi hua."
        ),
        "empty_status": "Is conversation ke liye abhi koi payment confirm nahi hai.",
    },
    "hi": {
        "clarify": "किस दिन या ट्रिप का भुगतान गलत लगा? कृपया तारीख या ट्रिप आईडी बताइए।",
        "unsafe": "मैं केवल इस खाते के सत्यापित ट्रिप और भुगतान रिकॉर्ड पर मदद कर सकता हूँ।",
        "other": "ट्रिप भुगतान, सर्ज, प्रोत्साहन या रद्दीकरण कटौती की जानकारी दीजिए।",
        "review": "मामला सहायता टीम की समीक्षा के लिए भेजा है। अतिरिक्त भुगतान अधिकृत नहीं हुआ है।",
        "empty_status": "इस बातचीत के लिए अभी कोई भुगतान पुष्ट नहीं है।",
    },
}


def status_reply(payments, language):
    if not payments:
        return TEXT[language]["empty_status"]
    chunks = []
    for payment in payments[:4]:
        amount, status = payment["amount"], payment["status"]
        if payment["confirmed"]:
            chunks.append(
                f"₹{amount}: PaySwift has confirmed payment."
                if language == "en"
                else f"₹{amount}: PaySwift ne payment confirm kiya hai."
                if language == "hinglish"
                else f"₹{amount}: PaySwift ने भुगतान पुष्ट किया है।"
            )
        else:
            chunks.append(
                f"₹{amount}: {status}. Settlement is not confirmed yet."
                if language == "en"
                else f"₹{amount}: {status}. Payment abhi confirm nahi hai."
                if language == "hinglish"
                else f"₹{amount}: {status}। भुगतान अभी पुष्ट नहीं है।"
            )
    return " ".join(chunks)


def outcome_reply(outcomes, language):
    parts = []
    for value in outcomes:
        if value["kind"] == "status":
            parts.append(status_reply(value["payments"], language))
            continue
        if value["kind"] == "review":
            parts.append(TEXT[language]["review"])
            continue
        details = []
        for item in value.get("items", []):
            if item["expected"] is not None and item["historical"] is not None:
                if language == "en":
                    details.append(
                        f"{item['source']}: expected ₹{item['expected']}, "
                        f"historical ₹{item['historical']}."
                    )
                elif language == "hinglish":
                    details.append(
                        f"{item['source']}: ₹{item['expected']} banta tha, "
                        f"₹{item['historical']} historical payout mila."
                    )
                else:
                    details.append(
                        f"{item['source']}: अपेक्षित ₹{item['expected']}, "
                        f"ऐतिहासिक भुगतान ₹{item['historical']}।"
                    )
        parts.extend(details[:6])
        kind, amount = value["kind"], value.get("amount", "0")
        if kind == "no_shortfall":
            reasons = value.get("reasons", [])
            parts.extend(reasons[:2])
            parts.append(
                "No outstanding adjustment is verified."
                if language == "en"
                else "Koi outstanding adjustment verify nahi hua."
                if language == "hinglish"
                else "कोई बकाया समायोजन सत्यापित नहीं हुआ।"
            )
        elif kind == "approval":
            parts.append(
                f"₹{amount} requires Ops approval; no payment is confirmed."
                if language == "en"
                else f"₹{amount} Ops approval ke liye gaya hai; payment confirm nahi hai."
                if language == "hinglish"
                else f"₹{amount} के लिए Ops की मंजूरी चाहिए; भुगतान पुष्ट नहीं है।"
            )
        elif kind == "authorized":
            parts.append(
                f"₹{amount} is queued for payment. Settlement is not confirmed yet."
                if language == "en"
                else f"₹{amount} payment queue mein hai. Settlement abhi confirm nahi hai."
                if language == "hinglish"
                else f"₹{amount} भुगतान की कतार में है। भुगतान अभी पुष्ट नहीं है।"
            )
    return " ".join(parts)[:5000]
