"""Plain-language education; policy facts come from the existing financial services."""

import re
from decimal import Decimal

from app.services.financial.calculator import cancellation_pay, completed_trip_pay
from app.services.financial.incentive import expected_incentive
from app.services.payment_authorization import AUTO_PAY_LIMIT


def educational_reply(state):
    extraction = state["extraction"]
    language = extraction.language
    topic = extraction.help_topic
    base = completed_trip_pay(Decimal(2), Decimal(1))
    extra = completed_trip_pay(Decimal(3), Decimal(1)) - base
    example = completed_trip_pay(Decimal(5), Decimal(1))
    distance_extra = example - base
    surge = completed_trip_pay(Decimal(5), Decimal("1.5"))
    bonus = expected_incentive(12)
    penalty = abs(cancellation_pay("cancelled_by_rider"))
    # The first version states the rule; the second teaches it through an example.
    knowledge = {
        "fare": {
            "en": (
                (
                    f"For a completed trip, the first 2 km pay ₹{base}. Add ₹{extra} "
                    f"for each km beyond 2 km. Multiply that total by the trip's surge "
                    f"rate, then round to the nearest rupee; half a rupee rounds up. "
                    f"This explains the rule, not your personal payment."
                ),
                (
                    f"A made-up example: a completed 5 km trip without extra surge "
                    f"earns ₹{base} for the first 2 km plus ₹{distance_extra} for the next 3 km: "
                    f"₹{example}. With a 1.5 surge rate, that becomes ₹{surge} after "
                    f"rounding. We check your actual trip separately."
                ),
            ),
            "hinglish": (
                (
                    f"Completed trip ke pehle 2 km ke ₹{base} milte hain. Uske baad har "
                    f"extra km ke ₹{extra} jodte hain. Phir trip ka surge rate lagta "
                    f"hai. Aakhir mein nearest rupee tak round karte hain; aadha rupee "
                    f"upar hota hai. Yeh rule hai, aapke payment ki confirmation nahi."
                ),
                (
                    f"Ek example lete hain: 5 km ki completed trip mein pehle 2 km ke "
                    f"₹{base}, aur agle 3 km ke ₹{distance_extra}. Total ₹{example}. "
                    f"Agar surge 1.5 "
                    f"ho, toh round karke ₹{surge}. Yeh sirf example hai; aapki trip "
                    f"alag se check hogi."
                ),
            ),
            "hi": (
                (
                    f"पूरी हुई ट्रिप के पहले 2 किमी के ₹{base} मिलते हैं। इसके बाद हर "
                    f"अतिरिक्त किमी के ₹{extra} जुड़ते हैं। फिर ट्रिप का सर्ज दर लगाया "
                    f"जाता है। अंत में निकटतम रुपये तक पूर्णांक करते हैं; आधा रुपया ऊपर "
                    f"जाता है। यह नियम है, आपके भुगतान की पुष्टि नहीं।"
                ),
                (
                    f"एक उदाहरण लें: 5 किमी की पूरी ट्रिप में पहले 2 किमी के ₹{base} और "
                    f"अगले 3 किमी के ₹{distance_extra}, यानी ₹{example}। सर्ज 1.5 हो तो पूर्णांक करने "
                    f"पर ₹{surge}। यह सिर्फ उदाहरण है; आपकी ट्रिप अलग से जाँची जाएगी।"
                ),
            ),
        },
        "surge": {
            "en": (
                (
                    "Surge increases the normal completed-trip fare by the rate saved "
                    "for that trip. A rate of 1 means no increase; 1.5 means "
                    "one-and-a-half times the fare. The recorded rate is used, not a "
                    "rate guessed from the message."
                ),
                (
                    f"Think of surge as extra pay on top of normal trip pay. For "
                    f"example, a 5 km trip normally earns ₹{example}. At 1.5 times, it "
                    f"becomes ₹{surge} after rounding. This example does not mean that "
                    f"amount is owed to you."
                ),
            ),
            "hinglish": (
                (
                    "Surge ka matlab normal trip pay par extra paisa. Trip ke record "
                    "mein jo rate hai wahi lagta hai: 1 par normal pay, 1.5 par uska "
                    "dedh guna. Message se rate guess nahi karte."
                ),
                (
                    f"Aasaan example: 5 km ki trip ka normal pay ₹{example} hai. Surge "
                    f"1.5 ho toh dedh guna, round karke ₹{surge}. Yeh samjhane ka "
                    f"example hai, aapka confirmed payment nahi."
                ),
            ),
            "hi": (
                (
                    "सर्ज का मतलब सामान्य ट्रिप राशि पर अतिरिक्त कमाई है। ट्रिप में "
                    "दर्ज दर इस्तेमाल होती है: 1 पर सामान्य राशि, 1.5 पर उसका डेढ़ "
                    "गुना। दर का अनुमान नहीं लगाया जाता।"
                ),
                (
                    f"आसान उदाहरण: 5 किमी की ट्रिप की सामान्य राशि ₹{example} है। सर्ज "
                    f"1.5 हो तो डेढ़ गुना करके, पूर्णांक करने पर ₹{surge} बनेंगे। यह "
                    f"उदाहरण है, आपका पुष्ट भुगतान नहीं।"
                ),
            ),
        },
        "incentive": {
            "en": (
                (
                    f"Complete at least 12 trips in one day, counted in India time, to "
                    f"qualify for a ₹{bonus} daily bonus. Cancelled trips do not count. "
                    f"Records decide the count."
                ),
                (
                    f"For example, 11 completed trips in a day do not qualify. 12 "
                    f"qualify for ₹{bonus}. Completing more does not multiply that "
                    f"daily bonus. This is an example, not a check of your trips."
                ),
            ),
            "hinglish": (
                (
                    f"India time ke hisaab se ek din mein kam se kam 12 completed trips "
                    f"par ₹{bonus} ka daily bonus milta hai. Cancelled trips count nahi "
                    f"hoti. Ginti records se check hoti hai."
                ),
                (
                    f"Example: ek din mein 11 completed trips par bonus nahi; 12 par "
                    f"₹{bonus}. Zyada trips par yeh daily bonus baar-baar nahi judta. "
                    f"Yeh example hai, aapki trips abhi check nahi ki hain."
                ),
            ),
            "hi": (
                (
                    f"भारत के समय के अनुसार एक दिन में कम से कम 12 पूरी ट्रिप पर "
                    f"₹{bonus} का दैनिक बोनस मिलता है। रद्द ट्रिप नहीं गिनी जातीं। "
                    f"गिनती रिकॉर्ड से जाँची जाती है।"
                ),
                (
                    f"उदाहरण: एक दिन में 11 पूरी ट्रिप पर बोनस नहीं; 12 पर ₹{bonus}। "
                    f"अधिक ट्रिप करने पर यह दैनिक बोनस बार-बार नहीं जुड़ता। यह उदाहरण "
                    f"है; आपकी ट्रिप अभी नहीं जाँची गई हैं।"
                ),
            ),
        },
        "penalty": {
            "en": (
                (
                    f"A rider-cancelled trip has a ₹{penalty} deduction. A "
                    f"customer-cancelled trip has no deduction under this rule. A "
                    f"duplicate deduction needs checking against the recorded trip and "
                    f"payout."
                ),
                (
                    f"For example, if the rider cancels, the rule deducts ₹{penalty}. "
                    f"If the customer cancels, this rule deducts ₹0. A deduction "
                    f"appearing twice should be checked, not assumed correct."
                ),
            ),
            "hinglish": (
                (
                    f"Rider trip cancel kare toh ₹{penalty} ki deduction hai. Customer "
                    f"cancel kare toh is rule ke hisaab se deduction nahi. Ek hi "
                    f"deduction do baar dikhe toh trip aur payment records check "
                    f"karenge."
                ),
                (
                    f"Example: aap cancel karein toh ₹{penalty} katte hain; customer "
                    f"cancel kare toh ₹0. Ek deduction do baar lage toh usse sahi maan "
                    f"nahi lenge, pehle record check hoga."
                ),
            ),
            "hi": (
                (
                    f"राइडर के ट्रिप रद्द करने पर ₹{penalty} की कटौती है। ग्राहक रद्द "
                    f"करे तो इस नियम में कटौती नहीं है। एक कटौती दो बार दिखे तो ट्रिप "
                    f"और भुगतान रिकॉर्ड जाँचे जाते हैं।"
                ),
                (
                    f"उदाहरण: आप रद्द करें तो ₹{penalty} कटेंगे; ग्राहक रद्द करे तो ₹0। "
                    f"एक कटौती दो बार लगे तो उसे सही नहीं मानेंगे, पहले रिकॉर्ड जाँचा "
                    f"जाएगा।"
                ),
            ),
        },
        "window": {
            "en": (
                (
                    "We check trips from the seven full days "
                    "before the date used for your message, in India time. "
                    "Today and future dates are excluded. Older cases may need support "
                    "review."
                ),
                (
                    "Think of a calendar: leave today out, then count yesterday and "
                    "the six days before it. Those seven days fit the automatic-check "
                    "window. This does not itself approve a payment."
                ),
            ),
            "hinglish": (
                (
                    "Aapka message jis date se check hota hai, usse pichhle 7 poore din "
                    "automatic payment ke liye check ho sakte hain, India time ke "
                    "hisaab se. Aaj aur future dates nahi. Purane case mein support "
                    "review lag sakta hai."
                ),
                (
                    "Calendar sochiye: aaj ko chhod dijiye. Kal se ginte hue pichhle 7 "
                    "din lijiye. In dinon ke claims automatic check ho sakte hain; "
                    "sirf date sahi hone se payment approve nahi hota."
                ),
            ),
            "hi": (
                (
                    "आपका संदेश जिस तारीख से जाँचा जाता है, उससे पहले के 7 पूरे दिन भुगतान "
                    "की तारीख सीमा में आते हैं, भारत के समय के अनुसार। आज और भविष्य की "
                    "तारीखें नहीं। पुराने मामले में सहायता टीम की समीक्षा लग सकती है।"
                ),
                (
                    "कैलेंडर सोचिए: आज को छोड़ दें। कल से पीछे के 7 दिन गिनें। इन "
                    "दिनों के दावों की स्वतः जाँच हो सकती है; सिर्फ तारीख सही होने से "
                    "भुगतान मंजूर नहीं होता।"
                ),
            ),
        },
        "approval": {
            "en": (
                (
                    f"A verified claim above ₹{AUTO_PAY_LIMIT} needs support approval. "
                    f"Smaller claims must still pass the other checks; only one "
                    f"automatic payment request per rider is allowed per real calendar "
                    f"day in India. Approval is not payment completion."
                ),
                (
                    "Think of two steps: first confirm what is owed, then decide who "
                    "can approve it. A larger amount needs a person to approve it. "
                    "Until that approval happens, payment has not started. There is no "
                    "guaranteed approval time."
                ),
            ),
            "hinglish": (
                (
                    f"Verified claim ₹{AUTO_PAY_LIMIT} se zyada ho toh support approval "
                    f"chahiye. Chhote claims mein bhi baaki checks lagte hain; India ki "
                    f"asli calendar date par ek rider ke liye ek hi automatic payment "
                    f"request ho sakti hai. Approval ka matlab payment complete hona "
                    f"nahi."
                ),
                (
                    "Do steps sochiye: pehle check ki kitna paisa baaki hai, phir uski "
                    "permission. Badi amount ke liye support ki permission chahiye. "
                    "Usse pehle payment shuru nahi hota. Approval ka pakka time nahi "
                    "bata sakte."
                ),
            ),
            "hi": (
                (
                    f"₹{AUTO_PAY_LIMIT} से अधिक के सत्यापित दावे को सहायता टीम की "
                    f"मंजूरी चाहिए। छोटे दावों पर भी बाकी जाँच जरूरी है; भारत के "
                    f"वास्तविक कैलेंडर दिन में प्रति राइडर एक ही स्वतः भुगतान अनुरोध हो "
                    f"सकता है। मंजूरी का मतलब भुगतान पूरा होना नहीं।"
                ),
                (
                    "दो कदम सोचिए: पहले जाँचें कि कितनी राशि बकाया है, फिर उसे देने की "
                    "अनुमति। बड़ी राशि को सहायता टीम की अनुमति चाहिए। उससे पहले भुगतान "
                    "शुरू नहीं होता। मंजूरी का निश्चित समय नहीं बता सकते।"
                ),
            ),
        },
        "payment": {
            "en": (
                (
                    "A verified difference means the records show money missing. "
                    "Approval means permission to pay. A queued request means payment "
                    "is waiting to be sent. Completed means the saved payment and "
                    "provider evidence support success. In this demo, even successful "
                    "PaySwift payments are simulated; no real bank money moves."
                ),
                (
                    "Think of ordering something: agreeing to send it is different "
                    "from it arriving. A payment request is also different from a "
                    "completed payment. If the final result is uncertain, we check it "
                    "before sending again so you are not paid twice for the same "
                    "claim."
                ),
            ),
            "hinglish": (
                (
                    "Difference verify hone ka matlab records mein paisa kam mila. "
                    "Approval ka matlab payment ki permission. Request taiyar hona "
                    "payment milna nahi hai. Payment complete tab kahenge jab saved "
                    "record aur provider ka record support karein. Is demo mein "
                    "PaySwift payment bhi simulated hai; bank mein real paise nahi "
                    "jaate."
                ),
                (
                    "Jaise koi cheez bhejne ka kehna aur uska pahunchna alag hai, "
                    "waise payment request aur payment complete hona alag hain. Final "
                    "result clear na ho toh dobara bhejne se pehle check karte hain, "
                    "taaki same claim ka do baar payment na ho."
                ),
            ),
            "hi": (
                (
                    "अंतर सत्यापित होने का मतलब रिकॉर्ड में कम राशि मिली। मंजूरी का "
                    "मतलब भुगतान की अनुमति। अनुरोध तैयार होना राशि मिलना नहीं है। पूरा "
                    "भुगतान तभी कहेंगे जब सहेजा रिकॉर्ड और प्रदाता का रिकॉर्ड उसका "
                    "समर्थन करें। इस डेमो में PaySwift भुगतान भी नकली परीक्षण है; बैंक "
                    "में वास्तविक राशि नहीं जाती।"
                ),
                (
                    "जैसे कोई चीज भेजने का कहना और उसका पहुँच जाना अलग है, वैसे भुगतान "
                    "अनुरोध और पूरा भुगतान अलग हैं। अंतिम परिणाम स्पष्ट न हो तो दोबारा "
                    "भेजने से पहले जाँचते हैं, ताकि एक दावे का दो बार भुगतान न हो।"
                ),
            ),
        },
    }
    recent = [m["text"] for m in state["history"] if m["sender"] != "RIDER"]
    if topic in knowledge:
        versions = knowledge[topic][language]
        index = 1 if extraction.simplify else 0
        if recent and versions[index] == recent[-1]:
            index = 1 - index
        return versions[index]
    answer = extraction.help_answer.strip()
    # Free-form general knowledge may never become an account/payment assertion.
    personal_payment = re.search(
        r"\b(your|aapka|aapke|aapki)\b.{0,100}"
        r"\b(payment|payout|balance|claim|adjustment|transfer)\b|"
        r"आप(?:का|के|की).{0,100}(?:भुगतान|राशि|दावे|दावा|पैसे)",
        answer,
        re.I,
    )
    if (
        answer
        and not personal_payment
        and not re.search(r"₹|\bT\d+\b|\b(paid|approved|succeeded)\b|ho chuka|हो चुका", answer, re.I)
    ):
        if not recent or answer != recent[-1]:
            return answer
    return {
        "en": (
            "I can explain that in simple words. Which part would you like "
            "help with? If you mean a particular payment, share its trip or "
            "date so I can check the facts."
        ),
        "hinglish": (
            "Main aasaan shabdon mein samjha sakta hoon. Kaunsa hissa clear "
            "nahi hai? Agar kisi payment ki baat hai toh trip ya date bata "
            "dijiye, taaki sahi record check ho."
        ),
        "hi": (
            "मैं आसान शब्दों में समझा सकता हूँ। कौन सा हिस्सा स्पष्ट नहीं है? "
            "किसी भुगतान की बात है तो ट्रिप या तारीख बताइए, ताकि सही रिकॉर्ड "
            "जाँच सकूँ।"
        ),
    }[language]
