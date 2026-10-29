# LangGraph dispute agent (Milestone 5)

See [local business reference clock and streamed activity](reference-clock.md) for
the current interactive demo behavior.

## Architecture

There is one StateGraph with four nodes: load_context, understand, investigate, and reply. START enters load_context. Understand conditionally routes missing information, status questions, greetings, and rejected instructions directly to reply; grounded complaints enter investigate, then reply and END. Financial outcomes inside investigation follow deterministic tool results. The graph has no planning/reflection loop, no model-controlled payment tools, and a recursion limit of eight. One extraction call is allowed per attempt, with at most three extraction attempts across durable retries by default.

State contains trusted rider/conversation/message identities, original text and aware vendor timestamp, bounded history, structured extracted context, missing fields, compact outcomes, and final reply. No checkpoint database or second history store exists. PostgreSQL conversations/messages remain authoritative. Message agent_state stores a validated extraction checkpoint so interrupted jobs can resume without repeating that model call.

The model only extracts intent, language, complaint types, literal date tokens, trip IDs, untrusted mentioned amounts, and corrections. The server resolves dates in IST against the effective business reference time (original received_at for evaluator requests), or the original utterance reference for a remembered relative date. Grounding rejects invented date tokens and trip IDs. Ambiguous or missing trip details prompt clarification; evidence-backed exceptions can be escalated. Fare claims are merged before investigation so model output cannot split one large fare discrepancy into smaller auto-pay requests. Monetary calculations, eligibility, payment amounts, daily reservations, and approval decisions remain in the existing financial and payment services.

## Groq configuration

The default is openai/gpt-oss-20b. GROQ_MODEL can select another compatible tool-calling Groq model. GROQ_API_KEY is read as a SecretStr through existing settings; it is never printed or recorded in traces. Temperature is zero, SDK retries are disabled, and output is parsed into a Pydantic Extraction schema. GPT-OSS 20B/120B use `ChatGroq.with_structured_output(method="json_schema", strict=True)`; other configured models retain function calling. Strict schema support is documented by [Groq](https://console.groq.com/docs/structured-outputs).

Groq's [tool-use documentation](https://console.groq.com/docs/tool-use/overview) lists GPT-OSS 20B support. The [deprecation history](https://console.groq.com/docs/deprecations) records the older Llama defaults' retirement for normal tiers, so those are not selected by default. [LangChain's ChatGroq structured-output reference](https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output) documents the function-calling interface used here. Model availability remains account-dependent and configurable.

Settings:

- GROQ_MODEL=openai/gpt-oss-20b
- GROQ_TIMEOUT_SECONDS=3
- AGENT_FOREGROUND_SECONDS=7
- AGENT_JOB_SECONDS=24
- AGENT_MAX_ATTEMPTS=3

A dedicated versioned system prompt, quickdrop-extraction-v1, separates rider data from policy. The prompt version is recorded with extraction decisions. Raw model messages and private reasoning are never persisted. External LangSmith tracing is disabled around extraction, even if tracing environment variables are set. Rider-facing financial statements come from English, Hindi, and Hinglish templates populated only with deterministic results. Mentioned amounts never become payout parameters.

## Tools and safety

AgentTools binds trusted identity and execution ownership once. Tools validate ClaimRequest identity, scope limits, and trip ownership. No caller can select another rider through a tool argument. No SQL or payment arithmetic exists in graph nodes.

- get_rider_profile reads the trusted account.
- get_rider_trips reads the bounded claim scope and rejects foreign ownership.
- get_payout_history reads only the trusted rider's source payout rows.
- reconcile_dispute invokes the existing deterministic engine and provider-evidence adapter.
- check_payment_eligibility reports whether deterministic verification is ready for authorization; it does not issue money.
- create_payment_intent calls existing authorize_payment, with a transaction-bound ownership/handling-mode guard.
- create_ops_escalation uses the existing pending-queue service.
- payment_status reads existing intents and pending approvals, without treating an intent as settlement.

There is no LLM-visible direct PaySwift HTTP mutation. Only the existing durable payment worker can send money. Before each mutation, ownership checks lock rider/message/conversation and verify the processing token, live lease, trusted owner, and AI mode. Payment authorization repeats that guard inside its transaction after the external ledger lookup. A stale graph or a HUMAN takeover cannot grant new authorization through an outdated token.

Source coverage is verified against the immutable approved CSV snapshot, scoped to requested rider dates and trips. The adapter compares canonical source records with PostgreSQL, including historical payout coverage. Missing files, partial imports, extra/mismatched historical entries, or unsupported source evidence prevent automatic payment. Approved rider-reference and T312538 normalization rules are reused without new generic conversions. Other ambiguous distances remain review cases.

Verified positive claims persist deterministic dispute IDs based on rider and logical source scope. Rephrased requests reuse those disputes; overlapping alternative scopes are also blocked by existing prior-payment reconciliation checks. Dispute items preserve engine evidence. Existing authorization logic still enforces the ₹200 full-dispute threshold, one AUTO reservation per actual IST day, whole-rupee amounts, provider history, and Ops approval. A pending or UNKNOWN payment cannot become another logical payout. A pending approval is visible in status replies without a fictional payment intent.

Zero outstanding balance yields an explanation, not an intent. Record disagreements, ownership/date conflicts, old/ineligible claims, data-quality ambiguity, and incomplete provider history produce genuine review entries where appropriate. Existing uncertain payments produce truthful verification-pending replies. Only SUCCEEDED intents with provider identity support a payment-confirmation statement.

## Webhook and durable continuation

POST /messages keeps the assignment body and `{reply}` response. Existing external message uniqueness, payload-conflict detection, short claim/completion transactions, and exact completed-response replay remain intact. HUMAN conversations bypass the graph entirely.

Messages in one conversation execute in stored order. A later turn waits outside transactions while an earlier agent turn is unfinished. Different conversations can progress through multiple worker processes. Ordinary duplicate deliveries do not launch another graph.

The foreground graph budget is seven seconds inside the existing eight-second webhook budget. If the graph or extraction cannot finish, the message remains durably RECEIVED with agent_state, next_processing_at, attempt count, and a cached processing acknowledgment. This acknowledgment is explicitly not a final resolution: processing_status is not COMPLETED. Retries replay the pending acknowledgment without starting another foreground execution. The shared worker claims and resumes due messages; after completion it persists the final AI message and replaces webhook_reply with the final result. A later duplicate then receives the final reply.

The worker in python -m app.workers.main alternates agent work and payment work. Message claims reuse PostgreSQL advisory/row locks and fenced processing tokens. Crashes leave a recoverable lease; no in-memory task is required for correctness. Normal deferred retries use bounded delays. After the configured extraction attempt budget, a real technical escalation is persisted and the message completes with a truthful support-review response. No result is discarded merely because a provider or model timed out.

The worker must run for deferred messages and queued payouts to progress. Deferred final replies are stored for UI reads or later webhook replay. The supplied vendor contract has no outbound-send API, so this milestone cannot push a second WhatsApp reply after an earlier HTTP 200 acknowledgment. That transport capability remains a concrete integration limitation; no delivery success is fabricated.

## Conversation memory and audit

The last twelve non-internal messages, current structured extraction, date provenance, and a bounded list of related dispute IDs support clarifications and follow-up status checks. New resolved threads are not silently reopened. A status question in a new thread can retrieve the rider's latest payments. Corrections replace the extracted claim scope before further investigation. Internal Ops notes are excluded from model context.

Existing agent_traces records message receipt, extraction and prompt version, actual read tools, financial verification, authorization/queue decisions, clarification requests, errors, and final replies. Credential key redaction distinguishes actual token credentials from harmless date_tokens entities. No model chain-of-thought, raw provider errors, API keys, or hidden reasoning is stored.

## Migration, Docker, and operation

Revision 5a6f842e91d0 follows 20af73f418ab. It adds agent_state JSONB, agent_attempts integer, next_processing_at aware datetime, and a due-message index to the existing messages table. No new table is added. Existing rows are preserved; legacy messages are not automatically treated as new agent jobs unless claimed through the current webhook.

All additive migrations have been applied to the local development database. Alembic check reports no model drift. Counts were preserved across every application table: 40 riders, 3,304 trips, 3,222 historical payout lines, and zero seeded conversation/payment history. Test records are confined to disposable databases.

The worker image builds successfully with the locked dependencies. Compose loads existing root/backend environment files for Groq settings, overrides database/provider hosts for service networking, and mounts data read-only at /app/data for coverage verification. Stop grace time is 45 seconds to cover a bounded agent attempt plus a payment attempt. PaySwift service files and definition are unchanged. API startup remains explicit; this milestone does not add a Compose API service or frontend integration.

From backend, start these in separate terminals:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
uv run python -m app.workers.main
```

Or start the built Compose worker with docker compose up -d worker. Privileged reads retain the existing local development guard; no Ops authentication or human messaging endpoints are added.

To roll back, stop API and worker writers, preserve unfinished agent checkpoints and leases, and prefer a forward fix. Downgrading to 20af73f418ab drops the new message metadata/index; never downgrade while deferred messages still need processing. No reset, truncate, or source CSV edit is required.

## Verification results

- Independent extraction/date validation and tool tests passed before graph integration.
- Final complete backend suite: 309 passed, 1 skipped in 142.08 seconds. The skipped case is the explicit real-provider opt-in test.
- Exact CI unit selection: 148 passed, 162 deselected, without database fixtures or live APIs.
- All 24 original conversation scenarios passed with extraction labels, real financial services, PostgreSQL isolation, and a controlled mock payment worker. Production prompts contain no reference IDs or expected amounts.
- Controlled real PaySwift sandbox test: 1 passed. It used a synthetic rider, ₹25 sandbox units, and a disposable PostgreSQL database, then verified ledger correlation and persisted success. No development financial records changed.
- Live Groq: synthetic greeting and synthetic Hinglish incentive extraction succeeded. No source rider/trip data was sent in live verification.
- Live Groq through the actual /messages route in a disposable database: HTTP 200, exact cached replay, two stored messages, four audit events, zero payment intents.
- Ruff lint/formatting, locked dependency consistency, Compose syntax, worker image build, migration head, and schema consistency passed.
- A 30 ms timeout test initially cancelled setup SQL rather than reaching the model. The regression now uses a 500 ms budget with a deliberately blocked model call and verifies durable resumption. The final suite passes.

Tests also cover multilingual replies, relative-date provenance, trip ownership, invented entities, explicit date conflicts, no-shortfall explanations, ₹25/₹150 adjustments, full-amount approvals, multiple simultaneous complaint types, UNKNOWN payments, repeated webhooks, prompt injection, malformed model output, HUMAN bypass, bounded model failure escalation, and trace completeness. Financial and payment-worker regression suites pass unchanged in behavior.

## Files

New: app/agent/{graph,state,nodes,routes,replies,prompts,llm,dates}.py, app/agent/tools/{investigation,coverage}.py and package initializers; migration 5a6f842e91d0_agent_message_jobs.py; tests/test_agent_{extraction,tools,graph,scenarios,webhook}.py; tests/fixtures/agent_extractions.json; this document.

Updated: app/core/config.py, app/models/message.py, app/models/agent_trace.py, app/services/message_service.py, app/services/payment_authorization.py, app/workers/main.py, backend environment/dependency files and README, tests/test_messaging.py, and docker-compose.yml. Earlier Milestone 4 work remains preserved. Frontend, source CSVs, financial calculation implementation, prior migrations, and payswift/ remain unchanged by this milestone.


## Worker troubleshooting

`make workers` waits for PostgreSQL, Redis and PaySwift through `make infra-up` before
starting the local worker. If running locally, stop the Compose worker with
`make worker-stop` to keep a single development worker. Stop an already running local
worker with Ctrl+C before restarting it after a code change.

Connection-refused warnings identify whether agent or payment work could not reach
PostgreSQL. Check infrastructure health and the configured PostgreSQL host/port.
Groq failures log only the exception class, HTTP status and a recognized machine error
code. Provider error messages, failed generations, prompts and rider contents are not
logged. A repeated HTTP 400 can therefore be diagnosed without exposing private input.

## Grounded corrections and rider summaries

Extraction prompt v2 treats the latest explicit scope as authoritative. A supplied
trip ID or date can answer an earlier clarification. The deterministic repair layer
removes invalid dates carried from history, replaces corrected dates, and drops
obsolete claims outside the newly supplied scope before checkpointing extraction.
It never invents a complaint kind when neither the current extraction nor prior
structured context supplies one. Literal dates, ownership, source coverage, amounts,
and payment authorization still require the existing deterministic checks.

Invalid calendar dates, unknown account trip IDs, conflicting recorded dates, and
missing supporting records have distinct localized responses. They do not become
financial approvals. An explicitly disputed record can still require human review.
A supplied date is sufficient for an ordinary payout investigation, even when the
model incorrectly classifies that dated payout complaint as an unrelated message.
Identifier-only follow-ups inherit the conversation language; new English prose
switches to English, and Hindi/Hinglish prose retains its language.

Main replies summarize verified expected pay, recorded historical pay, outstanding
amount, and the actual authorization/payment state. A single trip may be identified;
multi-trip calculations remain in dispute items and investigation details. Approval
responses explicitly state that payment has not been initiated. They do not promise
outbound notifications. Source counts and amounts asserted by riders are never used
as financial evidence. No existing records, source files, or payment-worker policy
are changed by these presentation and extraction rules.

Duplicate requests and timing questions use distinct rider responses. Same-case
follow-ups read the existing scoped payment/approval status instead of requesting
another authorization. Confirmed sandbox payments are identified as already paid;
unresolved approvals or payments do not receive a second adjustment. A timing
question reports the current blocker and explicitly avoids promising an ETA that
is absent from the records. Ambiguous requests in a new conversation require a
trip/date rather than guessing the rider's most recent payment. Record disputes
and new explicit scopes retain their existing investigation path. Prompt v3 also
requires respectful handling without accusing a rider of fraud or promising an
unsupported approval, payment, completion time, or notification.

## Educational questions

Prompt v4 adds a `help` intent for policy education and general factual questions.
Fare, surge, incentive, cancellation, date-window, approval and payment-state
explanations use localized application-owned policy text. Fare and bonus example
amounts come from the financial calculator; the approval threshold shares the
existing authorization constant. Examples are clearly distinguished from the
rider's own money. This path does not reconcile or authorize a claim.

A simpler follow-up uses an example rather than repeating the same explanation.
The last answer is checked to avoid an immediate verbatim repetition. General
knowledge answers are bounded, model-generated educational text, not verified
account evidence or a source of new company policy. They may not declare payments
paid or approved. Prompts require uncertainty when facts are unknown, no invented
current facts, no private credentials, and respectful language without jargon.
Actual scoped missing-fare complaints still enter investigation if misclassified
as help. Account status continues to use the existing scoped payment lookup.

The rider activity display remains collapsible and separate from message bubbles,
with short operation labels, no surrounding card, and smaller muted text. A second
copy of the active progress label is not shown below the activity list. Only public
operation progress is displayed, never private model reasoning.

## Prompt contract v6

Groq and Bedrock Nova share one versioned system prompt in `app/agent/prompts.py`.
The schema description and Nova tool description cover both request understanding
and educational questions. The prompt distinguishes the latest requested scope
from financial evidence, preserves date provenance, removes corrected entities,
and routes existing-claim duplicates and timing questions to status checks.
Greetings consistently use `help/general`. Unpaid order counts alone no longer
conflict with the rule requiring actual bonus intent for incentive classification.
Ambiguous bonus intent requires a focused clarification rather than a guess.

The contract requires plain language, contextual teaching, no immediate verbatim
repetition, no invented progress or personal financial facts, and explicit uncertainty
when evidence is absent. The operator-provided two-day estimate remains limited to
pending support approval, not provider completion or bank settlement. These prompt
instructions guide language understanding; financial eligibility, authorization,
identity, provider evidence and duplicate prevention remain application-enforced.


Day-wide PAYOUT complaints with order-count/target evidence widen to include daily incentive investigation. Counts in rider text never establish eligibility: completed source trips and existing incentive lines are reconciled by the financial engine. Explicit trip-only complaints do not widen.

Webhook limitation: the vendor stops retrying after 2xx and supplies no outbound final-message API. Durable completion and SSE serve the Rider UI but do not deliver a delayed final reply to that vendor. A pending acknowledgment must be reported separately from final original-request delivery.


## Conversation lifecycle

Dispute resolution and payment confirmation do not close a support thread. An active
conversation uses OPEN (or an active workflow status such as PAYMENT_PENDING or
AWAITING_APPROVAL); after its last payment completes it returns to OPEN. Its history,
claim references and provider-backed payment status remain available for follow-ups.
A new issue can be investigated in the same thread, with existing idempotency and
real-IST-day authorization limits unchanged. HUMAN mode accepts rider messages while
suppressing LangGraph replies.

The persisted conversation status RESOLVED means explicitly closed, distinct from a
dispute's RESOLVED status. Only authenticated Ops resolution closes a conversation;
there is no inactivity timer. Subsequent reconciliation cannot reopen a closed thread.
The Rider UI offers Start New Conversation for closed threads and keeps their audit
history unchanged. Previously closed threads are not silently rewritten or reopened.
Dispute/payment SSE notifications refresh their saved state; only the conversation's
source_status determines closure in the composer. A disconnected SSE stream alone
does not prevent sending an authorized message.


Clarification is turn-aware: the agent stores the outstanding question in conversation
context. If the rider says they cannot supply details, it acknowledges that response,
explains the limitation and offers an approximate-day alternative instead of replaying
the same question. The existing extraction call may draft a short acknowledgment or
question in clarification_answer; financial/state assertions are rejected from that
field. Verified financial decisions still use the existing outcome renderers. Pending
clarification clears when grounded scope becomes usable, including a no-shortfall result.
Missing details alone create no dispute, approval, escalation or payment intent.
