# Premature escalation investigation

Follow-up: [the local demo clock](reference-clock.md) lets new signed interactive
messages use the configured dataset reference. Original records below are unchanged;
evaluator requests still use their original event time.

## Evidence before changes

The reported conversation is `ad0d23cf-a839-4667-96fd-ff2c9d6da059` (R003).
The stored message timestamp is `2026-10-29T07:23:00.389Z`. The reference scenario
in `data/conversations.json` has timestamp `2026-09-22T09:05:00+05:30`.
Both are genuine timestamps of their respective events; they are not interchangeable.

The saved extraction was a SURGE complaint for T926334 with literal day `20`.
The trace proves the graph called `get_rider_trips`. The trip belongs to R003,
started on 20 September, has distance 6 km and surge multiplier 1.5.
The old date constraint interpreted bare `20` as 20 October, raised `ValueError`,
skipped payout-history retrieval, and took the date/ownership-conflict branch.
Reconciliation also returned `INELIGIBLE`: the September trip is outside the seven
completed IST dates before the genuine October event.

Dispute `cae9f815-cb5f-5944-93cc-ef7c9f543e49` is `ESCALATED`, with no verified amount.
Queue `0bfd0e6c-6f5c-4d4a-b14e-2cedaf77f51e` is a pending `escalation`, with no amount.
There is no payment intent for that dispute. The UI was misleading because the
conversation serializer converted AI-handled ESCALATED to AWAITING_APPROVAL.
Additionally, `approval_queue(escalation=True)` returned APPROVAL_REQUIRED even
though it stored an escalation. Groq did not write the generic rider response.

An earlier R003 conversation separately records three failed extraction attempts
followed by technical escalation. That is distinct from this date conflict and
from a policy-required financial approval.

## Actual execution path and fixes

1. `POST /messages` validates the payload. Explicit UI thread submissions require
   the selected rider's signed simulator context.
2. `message_service.claim` binds the trusted rider, vendor message ID, content and
   unchanged received_at to a durable lease. Duplicate delivery returns the saved reply.
3. `execute` checks mode/ownership and invokes LangGraph outside database transactions.
   The existing durable worker resumes deferred or failed work.
4. The graph loads context/profile, extracts structured intent, validates grounded
   scope, reads owned trips and payout history, and reconciles source/provider evidence.
   An explicit fare complaint with a grounded trip cannot be skipped by a model's
   generic other/status classification. Model output never authorizes money.
5. A bare day now constrains an identified trip's day without inventing a month.
   Explicit/relative dates still constrain the full date. Seven-day eligibility
   separately uses the original message timestamp, unchanged.
6. Known ownership/date conflicts use EvidenceConflict and route to escalation.
   Operational tool failures receive a sanitized error trace with tool name/error
   class and retry through the durable worker. Exhaustion is technical escalation.
7. Positive eligible balances persist source items. Authorization freshly reconciles
   under the rider lock and checks provider history, amounts, prior decisions, daily
   auto-payment reservations and in-flight intents. Only actual approval conditions
   return APPROVAL_REQUIRED. Escalations now return ESCALATED, including existing queues.
8. Automatic authorization creates a PENDING intent, delegated to the existing
   PaySwift worker. Stable dispute scope, intent idempotency, prior-source blockers
   and the unique daily reservation prevent duplicate payments. The graph never
   POSTs a provider payment. Only provider confirmation produces SUCCEEDED.
9. SSE progress comes from executed tools; final messages and state updates publish
   after commit. API/UI preserve ESCALATED as “Awaiting support review”, with no
   invented payment state or approval amount.

Read-only reconciliation at the fixture timestamp verifies **₹74 expected − ₹49
historical = ₹25 outstanding**. Isolated HTTP/graph tests create one AUTO/PENDING
intent, no Ops item, and one worker-confirmed SUCCEEDED payment. Repeated vendor
delivery does not create another intent. The actual October event remains ineligible
and now receives an explicit outside-window explanation, not financial approval.

## Explicit historical local replay

Run `make replay` from the root. It invokes `app.scripts.replay --local-test-mode`,
requires development mode and local PostgreSQL, and runs the existing 24-scenario
evaluator with every original received_at unchanged. The evaluator creates, migrates
and drops only a uniquely named quickdrop_test_* database. Extraction uses the
existing labels; PaySwift uses an in-memory HTTP mock. No live payment is issued.

Replay never changes the browser event clock, production eligibility, original
CSV/JSON fixtures, or existing application records. Live Groq availability and
real PaySwift network behavior are outside this controlled evaluator.
