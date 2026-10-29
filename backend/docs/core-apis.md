# Core APIs and conversation persistence (Milestone 3)

This milestone adds persistence and read APIs. The deterministic reply handler acknowledges concerns; it does not run reconciliation, authorize money, call an LLM, or contact PaySwift. The financial engine and source CSVs are unchanged. No new dependencies or tables are required.

## Apply and verify locally

Commands below are for the developer. Implementation did not start a server, run tests, or apply this migration.

```bash
cd backend
uv sync --locked
uv run alembic upgrade head
uv run alembic current
uv run alembic check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_messaging_unit.py tests/test_messaging.py -q
uv run pytest -q
```

Database tests create a disposable `quickdrop_test_*` database, migrate it, and remove it afterward. The configured PostgreSQL role needs permission to create databases. Tests never seed synthetic conversations into the development database.

For local manual inspection:

```bash
APP_ENV=development ENABLE_LOCAL_INTERNAL_READS=true \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Use port 8001 instead if another API process already owns 8000. Do not run concurrent servers against different code revisions during migration.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/messages \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"wamid.TEST001","rider_id":"R003","text":"Surge missing","received_at":"2026-09-22T09:05:00+05:30"}'
curl http://127.0.0.1:8000/trace/R003
curl http://127.0.0.1:8000/ops/pending
```

Repeat the exact POST to inspect cached replay. Manual POSTs deliberately persist real local conversation records. Do not use these curl commands against a production database.

## Endpoint inventory

Official contracts:

- `POST /messages`: validated webhook, returns only `{reply}` with HTTP 200 after successful commit.
- `GET /trace/{rider_id}`: chronological JSON array with `at`, `type`, `name`, `input`, `output`.
- `GET /ops/pending`: JSON array of pending or in-review queue items that have no resolution timestamp. Approval amounts are numeric rupees; escalation amounts are null.
- `GET /health`: existing PostgreSQL readiness check, HTTP 200 or 503.

Rider reads:

- Existing `GET /ui/riders`, `/ui/riders/{rider_id}`, `/ui/riders/{rider_id}/trips`, `/ui/riders/{rider_id}/payout-lines` remain unchanged.
- `GET /ui/riders/{rider_id}/conversations`.
- `GET /ui/conversations/{conversation_id}`.
- `GET /ui/conversations/{conversation_id}/messages`.
- `GET /ui/conversations/{conversation_id}/disputes`.

The last three require `?rider_id=R003`. A mismatched owner returns 404. Messages exclude internal Ops notes. Conversation context, webhook processing tokens, and cached response internals are not exposed.

Ops reads:

- `GET /ui/ops/overview` returns aggregate metrics from real records.
- `GET /ui/ops/conversations` supports rider_id, handling_mode (AI/HUMAN), and source conversation status.
- `GET /ui/ops/conversations/{id}` includes bounded message and dispute pages, including internal notes.
- `GET /ui/ops/cases` supports rider_id and queue status; joins queue entries to disputes.
- `GET /ui/ops/cases/{id}` returns a queue entry and its dispute identifiers/amounts.
- `GET /ui/ops/payouts` supports rider_id and payment status.
- `GET /ui/ops/payouts/{id}` returns existing intent details, without idempotency keys or processing leases.
- `GET /ui/ops/traces` supports rider_id, conversation_id, and type.

Collections return `{items,total,limit,offset}`. Default limit is 50, maximum 100. Assignment arrays are intentionally not wrapped. Sort keys always include an identifier to break timestamp ties. Conversation lists sort newest first; message and trace histories sort oldest first. Detail pages accept limit/offset for nested collections. Counts and page contents are separate SQL queries and may reflect concurrent writes.

## UI compatibility and trust boundaries

Frontend files remain unchanged and still use mocks. A future HTTP adapter must unwrap paginated collections. Existing rider records use rider_id/name/city/joined_on; the adapter can map rider_id to the mock interface's id. Conversation summaries supply the frontend's handler AI/OPS and its current status union. AWAITING_INFORMATION maps to OPEN. ESCALATED maps to HUMAN_HANDLING for human mode, otherwise AWAITING_APPROVAL. source_status retains the precise persisted status.

Dispute responses deliberately expose only persisted claimed/verified amounts and item evidence. Mock-only policy conclusions, dates, expected aggregates, approved adjustments, provider attempts, and reconciliation outcomes are not fabricated. They require future verified workflows and an adapter rather than dummy financial values. Internal money fields use Decimal strings; only the official pending contract requires JSON numbers.

The simulator's rider_id is not authentication. Existing development data routes retain their existing behavior; they are not suitable for public deployment. New conversation reads, official trace/pending reads, and all internal Ops reads require all three conditions: APP_ENV=development, ENABLE_LOCAL_INTERNAL_READS=true, and an actual loopback request client. The flag defaults to false. Privileged reads return 403 otherwise, including production. Do not expose the local process through a reverse proxy or tunnel. Disable proxy header trust for local inspection. Public webhook identity is trusted only under the assignment's simulated messaging-vendor contract. Replace these boundaries with authenticated vendor validation and server-side Rider/Ops sessions before deployment. Frontend route protection provides no backend authorization.

## Lifecycle and webhook transactions

Conversation service locks the rider row before finding or creating a conversation. The most recently updated conversation whose status is not RESOLVED is active; ties use UUID. If all conversations are resolved, the next distinct webhook starts a new conversation. Existing resolved conversations stay resolved. No human takeover or handback HTTP endpoints exist. The service also provides history, redacted structured context, and explicit lifecycle setters for future callers.

Processing has three phases:

1. A short transaction obtains a transaction-scoped advisory lock derived from the external message ID, locks the rider row, validates existing identity/content/received_at, and claims work. `INSERT ... ON CONFLICT` and the existing unique message_id constraint are the final duplicate barrier. A new incoming record and its message_in trace commit together. Processing state changes from RECEIVED to PROCESSING in that transaction. A random ownership token and a 30-second lease are persisted. Only completed messages have a final cached reply.
2. The deterministic handler executes with no session or transaction held. Future inference belongs at this seam; long inference will need lease renewal and a separate webhook deadline strategy.
3. A short transaction locks the rider/message/conversation, verifies ownership, stores the AI reply, caches the webhook response, marks COMPLETED, clears the lease, updates conversation time, and writes the reply trace atomically.

HUMAN mode stores the rider message and the truthful forwarding acknowledgment in webhook_reply and the reply trace. It creates no simulated AI message. The current handling mode is checked again during completion. Rider messages remain available in the Human Ops Inbox read API.

Completed retries return the exact cached reply. Conflicting rider IDs, text (including whitespace), or timestamps return 409. Equivalent timezone representations of the same instant compare equal. Legacy messages without received_at cannot prove an identical payload and return 409 rather than silently accepting a conflict.

Concurrent retries wait outside transactions in brief intervals. The entire processing budget is eight seconds, below the approximate ten-second vendor deadline. Work still owned by another request returns HTTP 503 with Retry-After: 1 and no final reply cache. The vendor must retry the same payload and message_id. Expired, RECEIVED, or FAILED work can be reclaimed. Ordinary failures mark FAILED and record a generic error. Cancellation or process termination can leave PROCESSING until its 30-second lease expires; a later retry recovers. Stale owners cannot overwrite a new owner or cached reply. No temporary acknowledgment is cached as a final reply.

PostgreSQL lock and statement timeouts bound contention. Advisory hash collisions can briefly serialize unrelated messages but cannot merge them; exact message IDs and stored payloads remain authoritative. All future conversation creators must use the rider-lock policy. Handlers must not perform external side effects until their own durable idempotency design exists. There is no payment or provider execution in this milestone.

## Audit and metrics

Trace service uses existing agent_traces, supports all five required types, and accepts structured object input/null and JSON-compatible output. Decimal, UUID, and aware datetime values serialize safely. Secret-bearing keys and private reasoning keys are recursively redacted on writes and reads. Non-JSON floats are rejected. Credential values must never be placed in free-form strings; key-based redaction cannot infer every secret in arbitrary text. Trace events use server event times; vendor received_at remains in the input and incoming message. Chronology is stable by created_at and id. No fake tool calls or financial decisions are generated.

Overview totals include disputes, pending approvals, unresolved escalations, active human conversations, and payment exceptions (FAILED/UNKNOWN/NEEDS_REVIEW). Confirmed amounts include only SUCCEEDED intents with provider ID and reconciliation timestamp. This is a read model of stored evidence, not an independent provider reconciliation.

## Migration and rollback

Revision `7d2f6419bc30` follows `078eb21553bb`. It adds nullable received_at, processing_token, and processing_expires_at columns to messages. Existing rows, tables, constraints, and applied migration history remain intact. No create_all, resets, or source-data changes occur. Stop webhook writers before rolling back code/schema. Export any new timestamp/lease metadata needed for investigation, then `uv run alembic downgrade 078eb21553bb`. Downgrade removes only the three new metadata columns; incoming content and cached replies remain. Prefer a forward fix once webhook traffic uses the new revision.

## Verification status

Static Ruff checks and syntax/OpenAPI checks are performed during implementation. No pytest tests, PostgreSQL migration commands, servers, or long-running processes are executed at the user's request. New tests cover validation, multi-turn persistence, duplicates, simultaneous requests, conflicting payloads, busy retry responses, expired leases, stale owners, failed handlers, atomic completion rollback, HUMAN behavior, resolved conversations, audit ordering/redaction, rider isolation, pagination, queue semantics, Ops metrics/details, and the temporary access guard. Runtime and database behavior remain unverified until the developer runs the commands above.

## File inventory

- New routers: `app/api/messages.py`, `trace.py`, `ops_pending.py`, `ui/__init__.py`, `ui/conversations.py`, `ui/ops.py`.
- New services: `app/services/message_service.py`, `conversation_service.py`, `trace_service.py`.
- New repositories: `app/repositories/conversations.py`, `messages.py`, `disputes.py`, `ops_queue.py`, `ops.py`, `pagination.py`.
- New schemas: `app/schemas/messages.py`, `conversations.py`, `traces.py`, `ops.py`.
- New access guard: `app/core/access.py`.
- New migration: `alembic/versions/7d2f6419bc30_webhook_recovery.py`.
- New tests: `tests/test_messaging.py`, `tests/test_messaging_unit.py`.
- Updated: `app/main.py`, `app/core/config.py`, `app/models/message.py`, `app/models/agent_trace.py`, `tests/test_api_unit.py`, `.env.example`, `README.md`, and this document.

Existing changes from earlier milestones and user edits remain preserved. Dependency manifests, lockfiles, frontend files, source CSVs, financial services, and the existing migration are unchanged by Milestone 3.
