# Local demo business clock

Local `.env` sets `APP_REFERENCE_TIME=2026-09-23T12:30:00+05:30`. Empty or unset means
normal event time; absent event time falls back to actual current time. Values must
be timezone-aware. Settings reject a configured reference clock unless
`APP_ENV=development`, so it cannot silently activate in production.

`app.core.clock` is the shared utility. Only authenticated interactive simulator
submissions (the signed rider context with an explicit conversation ID) opt into the
demo clock. Official `/messages` evaluator requests use their explicit `received_at`,
even when the demo clock is configured. No evaluator timestamps are rewritten.

For a new demo message the service saves the effective IST reference in its existing
JSON agent state. Retries and worker recovery reuse that snapshot even if `.env`
changes. The original `Message.received_at` remains the actual incoming timestamp.
The graph uses the snapshot for extraction and relative dates, and carries it as
`ClaimRequest.reference_time` into deterministic reconciliation and fresh payment
authorization. A request without that optional snapshot uses its original received_at.

Relative `kal`, `aaj`, and `20 tarikh` resolve against 23 September as 22 September,
23 September, and 20 September. The seven-day completed-date rule is unchanged:
20 September is eligible; 13 September is outside the window. This does not make
same-day trips eligible or modify any CSV, trip date, payout amount, or migration.

Audit/message creation timestamps, authentication, leases, retry schedules and
provider timestamps continue using real system time. **The daily automatic-payment
reservation date is the real authorization date in IST**, not the demo reference
date. Existing rider locks, the unique rider/day reservation, in-flight intent checks,
source coverage and provider reconciliation remain in force. Changing the demo date
cannot create a second automatic reservation on the same real payment date.

New historical demo investigations have a deterministic reference-scoped dispute key
so they can investigate without rewriting an old out-of-window dispute. Prior source
items/payment evidence and real-day reservations still block duplicate payments.
Old messages and disputes are never retroactively reprocessed or edited.

Missing scope, missing supporting records, or an ambiguous trip/date prompts a
clarifying question. A verified policy exception, disputed source evidence, an
outside-window claim, or exhausted technical retries can still require support.

The rider UI shows public investigation activity from actual progress events,
separate from the answer. It expands while working and collapses on completion.
The verified deterministic answer is saved first, then transported in 64-character
SSE chunks. This is response transport streaming, not streaming Groq's extraction
or private reasoning. Stable message IDs avoid duplicates; final text and database
refetch recover from dropped chunks or reconnects.

Restart the API and worker after configuring the clock. Existing completed webhook
IDs retain their cached replies; send a new message to investigate using the new clock.
`make replay` remains the isolated 24-scenario evaluator using original event times
and mocked payments, regardless of the interactive demo clock.
