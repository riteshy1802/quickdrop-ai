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


def status_reply(payments, language, *, duplicate=False, direct=False, focus="status"):
    duplicate = duplicate or focus == "duplicate"
    if not payments:
        if focus in {"duplicate", "timing"}:
            return {
                "en": (
                    "I could not identify an existing adjustment in this conversation. "
                    "Which trip or date do you mean? I need to verify that claim "
                    "before discussing another payment or its timing."
                ),
                "hinglish": (
                    "Is conversation mein existing adjustment identify nahi hua. Kis "
                    "trip ya date ki baat kar rahe hain? Doosra payment ya uska waqt "
                    "batane se pehle us claim ka status verify karna zaroori hai."
                ),
                "hi": (
                    "इस बातचीत में मौजूदा समायोजन की पहचान नहीं हुई। आप किस ट्रिप या "
                    "तारीख की बात कर रहे हैं? दूसरे भुगतान या उसके समय पर जवाब देने से "
                    "पहले उस दावे की स्थिति जाँचना जरूरी है।"
                ),
            }[language]
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
            if duplicate:
                chunks.append(
                    {
                        "en": (
                            "I checked the existing claim. I will not create a second "
                            "adjustment for the same amount while this one is unresolved."
                        ),
                        "hinglish": (
                            "Maine existing claim ka status check kiya. Jab tak yeh resolve "
                            "nahi hota, same amount ke liye doosri adjustment request nahi "
                            "banaunga."
                        ),
                        "hi": (
                            "मैंने मौजूदा दावे की स्थिति जाँची। जब तक यह हल नहीं होता, उसी "
                            "राशि के लिए दूसरा समायोजन अनुरोध नहीं बनाऊँगा।"
                        ),
                    }[language]
                )
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
                        f"Payment has not been initiated."
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
                        f"liye gaya hai. Abhi payment initiate nahi hua hai."
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
                        f"चाहिए। अभी भुगतान शुरू नहीं हुआ है।"
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
            if focus == "timing":
                if status == "AWAITING_APPROVAL":
                    chunks.append(
                        {
                            "en": (
                                "Approval is estimated to take up to 2 days and may happen sooner. "
                                "This is an estimate, not a guaranteed deadline. Payment has not "
                                "been initiated; approval is needed before it can start."
                            ),
                            "hinglish": (
                                "Approval mein aam taur par 2 din tak lag sakte hain, lekin jaldi "
                                "bhi ho sakta hai. Yeh estimate hai, exact waqt ki guarantee nahi. "
                                "Pehle approval chahiye; abhi payment initiate nahi hua hai."
                            ),
                            "hi": (
                                "मंजूरी में अनुमानित तौर पर 2 दिन तक लग सकते हैं, लेकिन जल्दी भी "
                                "हो सकती है। यह अनुमान है, समय की गारंटी नहीं। अभी भुगतान शुरू "
                                "नहीं हुआ है; पहले मंजूरी जरूरी है।"
                            ),
                        }[language]
                    )
                else:
                    chunks.append(
                        {
                            "en": (
                                "The records do not include a confirmed completion time, so I "
                                "cannot promise when this will finish."
                            ),
                            "hinglish": (
                                "Records mein complete hone ka confirmed time nahi hai, isliye "
                                "main exact waqt ka vaada nahi kar sakta."
                            ),
                            "hi": (
                                "रिकॉर्ड में पूरा होने का निश्चित समय नहीं है, इसलिए मैं सटीक समय "
                                "का वादा नहीं कर सकता।"
                            ),
                        }[language]
                    )
    return " ".join(chunks)


def outcome_reply(outcomes, language, *, focus="status"):
    parts = []
    for value in outcomes:
        if value["kind"] in {"invalid_date", "invalid_trip", "unmatched_trip", "no_records"}:
            parts.append(validation_reply(value, language))
            continue
        if value["kind"] == "clarify":
            parts.append(TEXT[language]["clarify"])
            continue
        if value["kind"] == "status":
            parts.append(
                status_reply(
                    value["payments"],
                    language,
                    duplicate=value.get("duplicate", False),
                    focus=focus,
                )
            )
            continue
        if value["kind"] == "review":
            if value.get("reason") == "outside_window":
                parts.append(TEXT[language]["outside_window"])
            parts.append(TEXT[language]["review"])
            continue
        items = value.get("items", [])
        if len(items) == 1 and re.fullmatch(r"T\d+", items[0]["source"]):
            parts.append(f"Trip {items[0]['source']}:")
        if value.get("expected") is not None and "penalty" not in value.get("claim_types", []):
            dates = value.get("dates", [])
            from datetime import date

            day = date.fromisoformat(dates[0]).strftime("%-d %B") if len(dates) == 1 else None
            expected, historical = value["expected"], value["historical"]
            if language == "en":
                scope = f" on {day}" if day else ""
                parts.append(
                    f"I checked your records{scope}. You should have received "
                    f"₹{expected}, but ₹{historical} was recorded as paid."
                )
            elif language == "hinglish":
                scope = f" {day} ke aapke orders" if day else " aapke records"
                parts.append(
                    f"Maine{scope} check kiye. Records ke hisaab se ₹{expected} milne"
                    f" chahiye the, lekin ₹{historical} hi mile hain."
                )
            else:
                parts.append(
                    f"मैंने आपके रिकॉर्ड जाँचे। आपको ₹{expected} मिलने चाहिए थे, "
                    f"लेकिन ₹{historical} का भुगतान दर्ज है।"
                )
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
            if language == "en":
                reason = (
                    "This exceeds the automatic payment limit"
                    if value.get("over_auto_limit")
                    else (
                        "Today's automatic payment allowance is already used or reserved; "
                        "only one automatic payment per rider per day is allowed"
                    )
                    if value.get("approval_reason")
                    == "Daily automatic payment allowance already used or reserved"
                    else "Support approval is required for this payment"
                )
                parts.append(
                    f"The ₹{amount} difference is verified. {reason}, so it has been "
                    f"sent to our support team for approval. Payment has not been "
                    f"initiated."
                )
            elif language == "hinglish":
                reason = (
                    "Yeh amount automatic payment limit se zyada hai"
                    if value.get("over_auto_limit")
                    else (
                        "Aaj automatic payment ki request pehle hi ban chuki hai. "
                        "Ek din mein ek hi automatic payment allowed hai"
                    )
                    if value.get("approval_reason")
                    == "Daily automatic payment allowance already used or reserved"
                    else "Is payment ke liye support team ki approval zaroori hai"
                )
                parts.append(
                    f"₹{amount} ka difference confirm hua hai. {reason}, isliye "
                    f"support team ki approval ke liye bhej diya hai. Abhi payment "
                    f"initiate nahi hua hai."
                )
            else:
                parts.append(
                    f"₹{amount} का अंतर सत्यापित है। इसे मंजूरी के लिए सहायता टीम को "
                    f"भेज दिया है। अभी भुगतान शुरू नहीं हुआ है।"
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
    return "\n\n".join(parts)[:5000]


def validation_reply(value, language):
    kind, supplied = value["kind"], value.get("value", "")
    if kind == "invalid_date":
        return {
            "en": (
                f"‘{supplied}’ is not a valid calendar date, so I cannot check a "
                f"claim for it. Please correct the date; you do not need to "
                f"resend details already supplied."
            ),
            "hinglish": (
                f"‘{supplied}’ valid calendar date nahi hai, isliye is date ka "
                f"claim check nahi kar sakta. Sirf sahi date bata dijiye; jo "
                f"details de chuke hain unhe dobara bhejne ki zaroorat nahi hai."
            ),
            "hi": (
                f"‘{supplied}’ मान्य तारीख नहीं है, इसलिए इस तारीख का दावा जाँचा "
                f"नहीं जा सकता। केवल सही तारीख बताइए; बाकी जानकारी दोबारा भेजने "
                f"की जरूरत नहीं है।"
            ),
        }[language]
    if kind == "invalid_trip":
        return {
            "en": (
                f"I could not find trip {supplied} in this account's records. I "
                f"cannot verify a payment claim for that ID. Please check the ID;"
                f" no payment has been requested for it."
            ),
            "hinglish": (
                f"Trip {supplied} is account ke records mein nahi mila. Is ID par"
                f" payment claim verify nahi ho sakta. ID check kar lijiye; iske "
                f"liye koi payment request nahi bheji gayi hai."
            ),
            "hi": (
                f"इस खाते के रिकॉर्ड में ट्रिप {supplied} नहीं मिली। इस आईडी के "
                f"लिए भुगतान का दावा सत्यापित नहीं हो सकता। कृपया आईडी जाँच लें; "
                f"इसके लिए भुगतान का अनुरोध नहीं भेजा गया है।"
            ),
        }[language]
    if kind == "unmatched_trip":
        dates = ", ".join(value.get("dates", []))
        if dates:
            return {
                "en": (
                    f"This trip is recorded on {dates}, which differs from the date "
                    f"you supplied. Which date should I check? I have kept your trip "
                    f"ID."
                ),
                "hinglish": (
                    f"Yeh trip records mein {dates} ki hai, jo aapki batayi date se "
                    f"alag hai. Kaunsi date check karoon? Trip ID mere paas hai."
                ),
                "hi": (
                    f"रिकॉर्ड में यह ट्रिप {dates} की है, जो बताई गई तारीख से अलग है।"
                    f" कौन सी तारीख जाँचूँ? ट्रिप आईडी मेरे पास है।"
                ),
            }[language]
        return {
            "en": (
                "That trip could not be verified for this account, so I cannot "
                "approve a payment for it. Please check the trip ID."
            ),
            "hinglish": (
                "Yeh trip is account ke liye verify nahi hui, isliye is par "
                "payment approve nahi kar sakta. Trip ID check kar lijiye."
            ),
            "hi": (
                "यह ट्रिप इस खाते के लिए सत्यापित नहीं हुई, इसलिए इसके लिए "
                "भुगतान मंजूर नहीं किया जा सकता। कृपया ट्रिप आईडी जाँचें।"
            ),
        }[language]
    return {
        "en": (
            "I checked the supplied date, but found no supporting trip "
            "records. I cannot verify this claim with the available data. "
            "Please check the date or share a trip ID for it."
        ),
        "hinglish": (
            "Maine batayi date check ki, lekin us din ke supporting trip "
            "records nahi mile. Available data se yeh claim verify nahi ho "
            "sakta. Date check kar lijiye ya us trip ki ID bata dijiye."
        ),
        "hi": (
            "मैंने बताई गई तारीख जाँची, लेकिन उस दिन के ट्रिप रिकॉर्ड नहीं "
            "मिले। उपलब्ध जानकारी से दावा सत्यापित नहीं हो सकता। कृपया तारीख"
            " जाँचें या ट्रिप आईडी बताइए।"
        ),
    }[language]
