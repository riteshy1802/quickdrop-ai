# LangGraph dispute agent (Milestone 5)

## Architecture

There is one StateGraph with four nodes: load_context, understand, investigate, and reply. START enters load_context. Understand conditionally routes missing information, status questions, greetings, and rejected instructions directly to reply; grounded complaints enter investigate, then reply and END. Financial outcomes inside investigation follow deterministic tool results. The graph has no planning/reflection loop, no model-controlled payment tools, and a recursion limit of eight. One extraction call is allowed per attempt, with at most three extraction attempts across durable retries by default.

State contains trusted rider/conversation/message identities, original text and aware vendor timestamp, bounded history, structured extracted context, missing fields, compact outcomes, and final reply. No checkpoint database or second history store exists. PostgreSQL conversations/messages remain authoritative. Message agent_state stores a validated extraction checkpoint so interrupted jobs can resume without repeating that model call.

The model only extracts intent, language, complaint types, literal date tokens, trip IDs, untrusted mentioned amounts, and corrections. The server resolves dates in IST against received_at, or the timestamp of the original rider utterance for a remembered relative date. Grounding rejects invented date tokens and trip IDs. Conflicting supplied trip dates are escalated. Fare claims are merged before investigation so model output cannot split one large fare discrepancy into smaller auto-pay requests. Monetary calculations, eligibility, payment amounts, daily reservations, and approval decisions remain in the existing financial and payment services.

## Groq configuration

The default is openai/gpt-oss-20b. GROQ_MODEL can select another compatible tool-calling Groq model. GROQ_API_KEY is read as a SecretStr through existing settings; it is never printed or recorded in traces. Temperature is zero, SDK retries are disabled, and output is parsed into a Pydantic Extraction schema through ChatGroq.with_structured_output(method="function_calling").

Groq's [tool-use documentation](https://console.groq.com/docs/tool-use/overview) lists GPT-OSS 20B support. The [deprecation history](https://console.groq.com/docs/deprecations) records the older Llama defaults' retirement for normal tiers, so those are not selected by default. [LangChain's ChatGroq structured-output reference](https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output) documents the function-calling interface used here. Model availability remains account-dependent and configurable.

Settings:

- GROQ_MODEL=openai/gpt-oss-20b
- GROQ_TIMEOUT_SECONDS=3
- AGENT_FOREGROUND_SECONDS=5.5
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

The foreground graph budget is 5.5 seconds inside the existing eight-second webhook budget. If the graph or extraction cannot finish, the message remains durably RECEIVED with agent_state, next_processing_at, attempt count, and a cached processing acknowledgment. This acknowledgment is explicitly not a final resolution: processing_status is not COMPLETED. Retries replay the pending acknowledgment without starting another foreground execution. The shared worker claims and resumes due messages; after completion it persists the final AI message and replaces webhook_reply with the final result. A later duplicate then receives the final reply.

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
