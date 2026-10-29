# Connected Rider/Ops UI and realtime events

The existing Next.js design now uses live FastAPI adapters. TanStack Query owns HTTP
reads and writes; PostgreSQL owns messages, disputes, Ops cases, sessions and payments.
There is no mock fallback when a request fails. Legacy `.mock.ts` adapters remain only
as fixtures for the older prototype tests and are not imported by connected pages.

## Run locally

Requirements: Python 3.12 and uv, Docker Compose, and Node 20.19+, 22.12+, or 24+.
Use the existing root `.env` and optional `backend/.env` for PostgreSQL, Groq and Ops
administrator credentials. `backend/.env.example` lists the backend settings.

```sh
make install
make infra-up
make migrate
make seed                 # only if assignment CSVs have not been imported
make seed-admin           # requires OPS_ADMIN_EMAIL and OPS_ADMIN_PASSWORD
```

Run these in separate terminals:

```sh
make backend
make workers
make frontend
```

Open `/rider` or `/ops/login` on the Next.js server at port 3000. No browser is opened
by the test suite. The existing PaySwift sandbox runs on port 8081. Normal automated
tests use a mock provider and never execute real payouts.

`frontend/.env.example` documents `BACKEND_URL` (default `http://127.0.0.1:8000`).
Next.js proxies HTTP and SSE from `/api/backend/*`; cookies therefore stay on the
frontend origin. For a separately hosted API, configure `NEXT_PUBLIC_API_URL` and
explicit credentialed `CORS_ORIGINS`. Never use a wildcard credentialed origin.
The API and frontend are started by the Makefile commands above; Compose currently
runs PostgreSQL, Redis, PaySwift and the optional container worker.

Set `REDIS_URL=redis://localhost:6379/0` locally. The Compose worker uses
`redis://redis:6379/0` and waits for Redis health. For multiple API processes, set one
shared random `DEMO_SESSION_SECRET` of at least 32 characters. If unset, the process
creates a random secret; restarting requires selecting the demo rider again.
Set `ENABLE_DEMO_WORKSPACE=false` to disable simulator identities.

## Authorization and subscriptions

`POST /ui/demo/rider` validates an existing demo rider and issues a signed, expiring,
HttpOnly SameSite cookie. Cookies are scoped by rider identity so separate simulator
tabs can select different riders without overwriting each other's identity. The demo
selector intentionally permits selecting assignment riders; it is not production
rider authentication. Tokens never appear in SSE URLs.

`POST /ui/riders/{rider_id}/conversations` creates a persisted empty conversation.
The UI opens its stream before enabling submission, so the conversation ID is known
before processing starts. `/messages` accepts an optional `conversation_id` only with
matching signed demo context. Omit that field for the unchanged assignment webhook
contract. An explicit scope cannot point to another rider's or a resolved thread.
The original response remains exactly `{reply}`.

- `GET /ui/conversations/{id}/events?rider_id=...` requires signed demo context and
  verifies conversation ownership in PostgreSQL. Its read transaction is released
  before streaming starts.
- `GET /ui/ops/events` requires the existing Ops session. The session is checked during
  streaming; expiration/logout closes the stream and clears protected frontend caches.
- Existing privileged Ops reads/actions retain server authorization.
- `/trace/{rider_id}` and `/ops/pending` retain their assignment response contracts.
- Rider conversation reads and `/ui/conversations/{id}/payouts` return real persisted
  records, excluding internal notes. The old explicitly enabled local read guard remains
  available for development tools; SSE always requires signed context.

Responses use `text/event-stream`, named events, event IDs, a two-second retry hint,
roughly 15-second heartbeats, no-cache headers and `X-Accel-Buffering: no`. Every
subscription owns its Redis PubSub connection and unsubscribes/closes on disconnect.
`ready`, `unavailable` and `session.expired` are connection-control signals.

## Event contracts

`app/realtime/events.py` defines the Pydantic envelope; the frontend validates the
matching contract with Zod in `src/lib/realtime/events.ts`.

Each event contains `event_id`, `event_type`, `conversation_id`, `rider_id`, `run_id`,
`sequence`, UTC `timestamp`, and explicitly allowed `data` fields. Identifiers correlate
runs and persisted messages. Events never contain session cookies, credentials, raw
model output, hidden reasoning, tool arguments or private-note text.

Published events include:

- Agent start/status, visible message delta/completion, completion and processing failure.
- Message creation and conversation changes, takeover and handback.
- Dispute changes and Ops case creation/updates.
- Payment state changes and provider reconciliation.

Channels are `quickdrop:conversation:{id}` and `quickdrop:ops:events`. Internal-note
notifications go only to the authenticated Ops channel. Shared notifications contain
IDs and statuses; clients fetch authorized records for message bodies and details.

SQLAlchemy flush listeners prepare minimal snapshots. The outer commit schedules
publication; rollbacks discard notifications. This covers the API and durable worker
without duplicating service logic. Redis errors are bounded and logged without
credentials. A completed database action is never rolled back because Redis is down.
Notifications can be lost during outages or process termination; this is deliberate
best-effort Pub/Sub rather than a durable event outbox.

## Agent output and human control

LangGraph uses its asynchronous `updates` stream. Only allowlisted operation statuses
leave the graph; extraction and tool results stay in the existing audit service.
Progress is emitted when the corresponding operation starts. Deferred jobs report
verification pending, rather than inventing running tools.

The current Groq call returns structured intent/claim data. Rider-facing replies are
constructed deterministically by the existing grounded templates. Consequently each
final reply is transported in ordered 64-character `agent.message.delta` chunks,
followed by completion, after its authoritative message commits. These are chunks of
an already verified answer, not incremental generation from a response LLM. Extraction
and private reasoning are never streamed. The public investigation activity panel
shows actual operation statuses separately and collapses when the answer completes.

The same persisted message ID identifies the delta and completion. `/messages`, saved
history and the final event agree. Existing ownership/version locks still prevent
stale graph writes or new payment authorization after takeover. Events carry that
control version; clients discard delayed AI output from an earlier ownership version,
including after handback. Human replies use OPS bubbles and refresh the Rider chat.

## Frontend recovery

One EventSource follows the active Rider conversation; one shared connection follows an
authenticated Ops console. Effects close listeners on identity changes and unmount.
The adapter validates payloads, bounds its event-ID deduplication set, checks per-run
sequence order, and discards temporary text when a gap occurs. Final completion and
query refetches reconcile against PostgreSQL by stable message ID, avoiding duplicates
between HTTP and SSE.

Reconnect clears temporary buffers and invalidates relevant queries. Fifteen-second
query refreshes and focus refreshes recover saved changes when realtime is unavailable.
There is no `Last-Event-ID` replay claim: Redis Pub/Sub cannot replay missed events.
Signed rider context is renewed through a TanStack mutation when it expires. Ops
sessions remain server-managed; no browser storage contains session secrets.

Outgoing Rider messages appear immediately as temporary pending rows keyed by the
original webhook ID; retries reuse that ID. Human replies and notes use a stable
client UUID across retries. Financial values remain server-derived: unknown evidence
is shown as unavailable, not zero; approval stays pending until provider confirmation.
Per-item evidence and recorded payment attempts come from actual backend records and
traces. There are no fabricated policy checks, trace durations or provider health data.

The current Ops UI expects one workspace snapshot. Its live adapter reads all paginated
collections and conversation histories into one TanStack query. This is suitable for
the assignment dataset, but large deployments should split it into page-specific
queries and server-side table filters. No second authoritative store is maintained.

## Verification

Backend tests cover actual Redis fan-out to two subscribers, publisher failure, event
serialization, authorization, disconnect/cancellation cleanup, session expiry,
post-commit/rollback boundaries, note privacy, safe output identity, worker transitions,
and the full HTTP Rider/Ops/worker flow. PostgreSQL fixtures use disposable databases.
Frontend Vitest/jsdom tests cover real adapters, Query hooks, pending states, typed
parsing, sequence gaps, duplicate suppression, reconnect, rider switching, listener
cleanup, session expiry, stale control versions, and multiple independent clients.
No Chrome or other browser UI is opened. Real browser layout testing remains manual.

GitHub Actions now supplies Redis beside PostgreSQL and runs `npm test` alongside lint,
TypeScript and the production build. Run locally:

```sh
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
cd ../frontend
npm run lint
npm test
npm run typecheck
npm run build
```

Provider health monitoring, notification persistence/read tracking, full containerized
API/frontend startup and incremental LLM response generation remain outside this change.
The UI labels unavailable provider observations honestly instead of inventing them.

Implementation references: [Redis asyncio](https://redis.io/docs/latest/develop/clients/redis-py/async/),
[Redis Pub/Sub delivery](https://redis.io/docs/latest/develop/use-cases/pub-sub/redis-py/),
and [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming).
