"""Render only deterministic outcomes. The LLM never writes financial statements."""

import re

TEXT = {
    "en": {
        "clarify": (
            "I can help check this. Could you share the trip ID or date so I "
            "can find the right records?"
        ),
        "unsafe": "I can only help with this account using verified trip and payout records.",
        "other": "I can help with trip payouts, surge, incentives, or cancellation deductions.",
        "review": (
            "Our support team needs to review the details before we can "
            "confirm an additional payment."
        ),
        "outside_window": (
            "This claim is not eligible for automatic payment because the "
            "trip is outside the seven-day eligibility window."
        ),
        "empty_status": (
            "I checked this conversation, but there is no confirmed payment to share yet."
        ),
    },
    "hinglish": {
        "clarify": (
            "Main check kar deta hoon. Aap trip ID ya date bata dijiye, taaki "
            "sahi payment dekh sakoon."
        ),
        "unsafe": (
            "Main sirf is account ke verified trip aur payout records par madad kar sakta hoon."
        ),
        "other": "Trip payout, surge, incentive ya cancellation penalty ki details bata dijiye.",
        "review": (
            "Maine aapka case support team ko review ke liye bheja hai. Abhi "
            "koi extra payment confirm nahi hua hai."
        ),
        "outside_window": (
            "Yeh claim automatic payment ke liye valid nahi hai, kyunki trip "
            "saat din ki eligibility window ke bahar hai."
        ),
        "empty_status": (
            "Maine is conversation ka status dekha, lekin abhi kisi payment ki"
            " confirmation nahi mili hai."
        ),
    },
    "hi": {
        "clarify": (
            "मैं इसकी जाँच कर सकता हूँ। कृपया ट्रिप की आईडी या तारीख बताइए, ताकि सही भुगतान देख सकूँ।"
        ),
        "unsafe": "मैं केवल इस खाते के सत्यापित ट्रिप और भुगतान रिकॉर्ड पर मदद कर सकता हूँ।",
        "other": "ट्रिप भुगतान, सर्ज, प्रोत्साहन या रद्दीकरण कटौती की जानकारी दीजिए।",
        "review": ("मामला सहायता टीम की समीक्षा के लिए भेजा है। अतिरिक्त भुगतान अधिकृत नहीं हुआ है।"),
        "outside_window": "यह ट्रिप सात दिन की पात्रता अवधि से बाहर है।",
        "empty_status": "इस बातचीत के लिए अभी कोई भुगतान पुष्ट नहीं है।",
    },
}


def status_reply(payments, language, *, duplicate=False, direct=False):
    if not payments:
        return TEXT[language]["empty_status"]
    chunks = []
    for payment in payments[:4]:
        amount, status = payment["amount"], payment["status"]
        if not payment["confirmed"] and payment.get("provider_check") == "CONFIRMED":
            chunks.append(
                {
                    "en": (
                        f"PaySwift's sandbox reports that your ₹{amount} payment completed. "
                        "Our saved payment record still needs final verification. "
                        "We will not send the same payment again while that check is pending."
                    ),
                    "hinglish": (
                        f"PaySwift sandbox ke record mein aapke ₹{amount} ka payment ho chuka hai. "
                        "Hamare saved payment record ki final verification abhi baaki hai. "
                        "Is check ke dauraan same payment dobara nahi bhejenge."
                    ),
                    "hi": (
                        f"PaySwift सैंडबॉक्स के अनुसार आपके ₹{amount} का भुगतान पूरा हो चुका है। "
                        "हमारे सहेजे गए रिकॉर्ड की अंतिम जाँच अभी बाकी है। "
                        "इस जाँच के दौरान वही भुगतान दोबारा नहीं भेजा जाएगा।"
                    ),
                }[language]
            )
            continue
        if payment["confirmed"]:
            source = ", ".join(payment.get("sources", [])[:3])
            scope = f" ({source})" if source else ""
            current = payment.get("provider_check") == "CONFIRMED"
            if not current:
                chunks.append(
                    {
                        "en": (
                            f"Your ₹{amount} payment{scope} was previously confirmed in "
                            f"PaySwift's sandbox. I cannot verify it against the live provider"
                            f" ledger right now. We will not send another payment while this "
                            f"is checked."
                        ),
                        "hinglish": (
                            f"Aapke ₹{amount} ka payment{scope} pehle PaySwift sandbox mein "
                            f"confirm hua tha. Abhi live payment record se dobara verify nahi "
                            f"ho pa raha hai. Isliye check kiye bina dobara payment nahi "
                            f"bhejenge."
                        ),
                        "hi": (
                            f"आपके ₹{amount} का भुगतान{scope} पहले PaySwift सैंडबॉक्स में "
                            f"पुष्ट हुआ था। अभी इसकी दोबारा जाँच नहीं हो पा रही है। जाँच के "
                            f"बिना दोबारा भुगतान नहीं भेजा जाएगा।"
                        ),
                    }[language]
                )
                continue
            if duplicate:
                expected, historical = payment.get("expected"), payment.get("historical")
                if expected and expected != "0" and historical and not historical.startswith("-"):
                    chunks.append(
                        {
                            "en": (
                                f"For this claim, you should have received ₹{expected}, and "
                                f"₹{historical} was originally recorded as paid."
                            ),
                            "hinglish": (
                                f"Is claim mein aapko ₹{expected} milne chahiye the aur "
                                f"₹{historical} ka payment pehle record hua tha."
                            ),
                            "hi": (
                                f"इस दावे में आपको ₹{expected} मिलने चाहिए थे और पहले "
                                f"₹{historical} का भुगतान दर्ज था।"
                            ),
                        }[language]
                    )
                chunks.append(
                    {
                        "en": (
                            f"I checked this claim{scope}. The ₹{amount} difference has "
                            f"already been paid and matches PaySwift's ledger. No additional "
                            f"amount is due for this claim, so I will not request the same "
                            f"payment again. This is a sandbox payment; no real bank transfer "
                            f"occurred."
                        ),
                        "hinglish": (
                            f"Maine yeh claim{scope} dobara check kiya. Iske ₹{amount} ka "
                            f"baaki payment pehle hi ho chuka hai aur PaySwift ke record se "
                            f"bhi confirm hai. Is claim par ab koi amount baaki nahi hai, "
                            f"isliye same payment dobara nahi bhejenge. Yeh sandbox payment "
                            f"hai; real bank transfer nahi hua hai."
                        ),
                        "hi": (
                            f"मैंने यह दावा{scope} दोबारा जाँचा। ₹{amount} का बकाया भुगतान "
                            f"पहले ही हो चुका है और PaySwift के रिकॉर्ड से भी पुष्ट है। इस "
                            f"दावे पर अब कोई राशि बकाया नहीं है, इसलिए दोबारा भुगतान नहीं भेजा"
                            f" जाएगा। यह सैंडबॉक्स भुगतान है; वास्तविक बैंक हस्तांतरण नहीं हुआ"
                            f" है।"
                        ),
                    }[language]
                )
            else:
                prefix = (
                    {"en": "Yes. ", "hinglish": "Haan, ", "hi": "हाँ, "}[language] if direct else ""
                )
                chunks.append(
                    prefix
                    + {
                        "en": (
                            f"Your ₹{amount} payment{scope} has completed in the PaySwift "
                            f"sandbox. I checked both the saved payment and the provider "
                            f"ledger. This is a test payment, so no real money was transferred"
                            f" to your bank account."
                        ),
                        "hinglish": (
                            f"aapke ₹{amount} ka payment{scope} PaySwift sandbox mein ho chuka"
                            f" hai. Maine saved payment aur PaySwift ka record dono check kiye"
                            f" hain. Yeh test payment hai, isliye aapke bank account mein real"
                            f" paise transfer nahi hue hain."
                        ),
                        "hi": (
                            f"आपके ₹{amount} का भुगतान{scope} PaySwift सैंडबॉक्स में पूरा हो "
                            f"चुका है। मैंने सहेजे गए भुगतान और PaySwift के रिकॉर्ड दोनों "
                            f"जाँचे हैं। यह परीक्षण भुगतान है, इसलिए आपके बैंक खाते में "
                            f"वास्तविक राशि नहीं भेजी गई है।"
                        ),
                    }[language]
                )
        else:
            messages = {
                "en": {
                    "NEEDS_REVIEW": (
                        f"We confirmed that ₹{amount} is owed to you, but the payment is on hold "
                        "for support verification. It has not been confirmed as paid. "
                        "We will not submit it again until it is checked, "
                        "to avoid a duplicate payment."
                    ),
                    "UNKNOWN": (
                        f"We are verifying the final status of your ₹{amount} payment to "
                        f"avoid paying twice. Receipt is not confirmed yet."
                    ),
                    "AWAITING_APPROVAL": (
                        f"Your ₹{amount} adjustment needs support approval before payment. "
                        f"Payment is not confirmed yet."
                    ),
                    "FAILED": (
                        f"Your ₹{amount} payment could not be completed. Support needs to "
                        f"review it; no payment is confirmed."
                    ),
                    "pending": (
                        f"Your payment request for ₹{amount} is ready. The payment has not been "
                        f"confirmed yet."
                    ),
                },
                "hinglish": {
                    "NEEDS_REVIEW": (
                        f"Records ke hisaab se aapke ₹{amount} baaki hain, lekin payment abhi hold "
                        "par hai. Support team ko final status verify karna hai. Payment ho chuka "
                        "hai, yeh abhi confirm nahi hai. Duplicate payment avoid karne ke liye "
                        "check hone tak dobara payment nahi bhejenge."
                    ),
                    "UNKNOWN": (
                        f"Aapke ₹{amount} payment ki final status verify ho rahi hai, taaki "
                        f"duplicate payment na ho. Payment milne ki confirmation abhi nahi "
                        f"hai."
                    ),
                    "AWAITING_APPROVAL": (
                        f"Aapka ₹{amount} adjustment payment se pehle support approval ke "
                        f"liye gaya hai. Payment abhi confirm nahi hai."
                    ),
                    "FAILED": (
                        f"Aapka ₹{amount} payment complete nahi ho saka. Support team ko isse"
                        f" check karna hoga; payment abhi confirm nahi hai."
                    ),
                    "pending": (
                        f"Aapke ₹{amount} ka payment bhejne ki request taiyar hai. Payment abhi "
                        f"confirm nahi hai."
                    ),
                },
                "hi": {
                    "NEEDS_REVIEW": (
                        f"आपके ₹{amount} का समायोजन सत्यापित है। भुगतान की अंतिम स्थिति की "
                        f"जाँच जारी है, ताकि दोबारा भुगतान न हो। राशि मिलने की पुष्टि अभी "
                        f"नहीं हुई है।"
                    ),
                    "UNKNOWN": (
                        f"आपके ₹{amount} के भुगतान की अंतिम स्थिति जाँची जा रही है, ताकि "
                        f"दोबारा भुगतान न हो। राशि मिलने की पुष्टि अभी नहीं हुई है।"
                    ),
                    "AWAITING_APPROVAL": (
                        f"आपके ₹{amount} के समायोजन को भुगतान से पहले सहायता टीम की मंजूरी "
                        f"चाहिए। भुगतान अभी पुष्ट नहीं है।"
                    ),
                    "FAILED": (
                        f"आपका ₹{amount} का भुगतान पूरा नहीं हो सका। सहायता टीम को जाँच करनी "
                        f"होगी; भुगतान अभी पुष्ट नहीं है।"
                    ),
                    "pending": (
                        f"आपके ₹{amount} का समायोजन भुगतान की कतार में है। भुगतान अभी पुष्ट नहीं है।"
                    ),
                },
            }
            label = "NEEDS_REVIEW" if status == "SUCCEEDED" else status
            chunks.append(messages[language].get(label, messages[language]["pending"]))
    return " ".join(chunks)


def outcome_reply(outcomes, language):
    parts = []
    for value in outcomes:
        if value["kind"] == "clarify":
            parts.append(TEXT[language]["clarify"])
            continue
        if value["kind"] == "status":
            parts.append(
                status_reply(value["payments"], language, duplicate=value.get("duplicate", False))
            )
            continue
        if value["kind"] == "review":
            if value.get("reason") == "outside_window":
                parts.append(TEXT[language]["outside_window"])
            parts.append(TEXT[language]["review"])
            continue
        details = []
        for item in value.get("items", []):
            if item["expected"] is not None and item["historical"] is not None:
                if language == "en":
                    details.append(
                        f"For {item['source']}, you should have received ₹{item['expected']}. "
                        f"Our records show that ₹{item['historical']} was paid."
                    )
                elif language == "hinglish":
                    details.append(
                        f"{item['source']} ke liye aapko ₹{item['expected']} milne chahiye the. "
                        f"Records mein ₹{item['historical']} ka payment dikh raha hai."
                    )
                else:
                    details.append(
                        f"{item['source']} के लिए आपको ₹{item['expected']} मिलने चाहिए थे। "
                        f"रिकॉर्ड में ₹{item['historical']} का भुगतान दर्ज है।"
                    )
        parts.extend(details[:6])
        kind, amount = value["kind"], value.get("amount", "0")
        if kind == "no_shortfall":
            reasons = value.get("reasons", [])
            for reason in reasons[:2]:
                count = re.fullmatch(r"(\d+) completed trips on this IST date", reason)
                if language == "en":
                    parts.append(
                        f"Your records show {count[1]} completed trips on that date."
                        if count
                        else reason
                    )
                elif count:
                    parts.append(
                        f"Is din {count[1]} completed trips record mein hain."
                        if language == "hinglish"
                        else f"इस दिन {count[1]} पूरी की गई ट्रिप दर्ज हैं।"
                    )
            parts.append(
                "I checked the records and could not find any unpaid difference."
                if language == "en"
                else "Maine records check kiye, lekin koi baaki payment nahi mila."
                if language == "hinglish"
                else "मैंने रिकॉर्ड जाँचे, लेकिन कोई बकाया राशि नहीं मिली।"
            )
        elif kind == "approval":
            parts.append(
                f"We found ₹{amount} still owed to you. Our support team needs to "
                f"approve it before payment can proceed."
                if language == "en"
                else (
                    f"Aapke ₹{amount} baaki hain. Payment se pehle support team ki "
                    f"manzoori chahiye. Payment abhi confirm nahi hai."
                )
                if language == "hinglish"
                else (
                    f"आपके ₹{amount} बकाया हैं। भुगतान से पहले सहायता टीम की मंजूरी "
                    f"चाहिए। भुगतान अभी पुष्ट नहीं है।"
                )
            )
        elif kind == "authorized":
            parts.append(
                f"We confirmed that ₹{amount} is still owed to you and queued it "
                f"for payment. We are waiting for payment confirmation."
                if language == "en"
                else (
                    f"Aapke ₹{amount} baaki hain aur payment bhejne ki request taiyar "
                    f"hai. Payment abhi confirm nahi hai."
                )
                if language == "hinglish"
                else (
                    f"आपके ₹{amount} बकाया हैं और भुगतान का अनुरोध तैयार है। भुगतान की पुष्टि अभी नहीं हुई है।"
                )
            )
    return " ".join(parts)[:5000]
