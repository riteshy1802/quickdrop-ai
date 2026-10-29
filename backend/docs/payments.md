# PaySwift and durable payment worker (Milestone 4)

## Scope and implementation status

Payment creation is available only through the deterministic internal authorization service. There is no HTTP send-money endpoint. `/messages` remains an acknowledgment-only webhook. No LangGraph, LLM, human approval mutations, frontend integration, or payment notifications are added.

Static checks are executed during implementation. Per the developer's instruction, no pytest tests, migration against PostgreSQL, server/worker process, Docker build, PaySwift health request, or sandbox payout is executed. Runtime behavior remains unverified until the commands below are run. A real sandbox integration test is provided behind an explicit opt-in flag.

## Developer verification commands

From the repository root, PostgreSQL and PaySwift must already be available. Install and migrate before starting a worker:

```bash
cd backend
uv sync --locked
uv run alembic upgrade head
uv run alembic current
uv run alembic check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_payswift.py tests/test_payments_database.py -q
uv run pytest -q
```

The normal tests use httpx.MockTransport and a disposable quickdrop_test_* PostgreSQL database. The database role needs CREATEDB. Synthetic records never enter the development database. The real-provider test is skipped unless explicitly enabled.

Run the worker in its own terminal:

```bash
cd backend
uv run python -m app.workers.main
```

Or use Compose after migration:

```bash
docker compose build worker
docker compose up -d worker
```

For a fresh Docker-only setup, migrate through the worker image first:

```bash
docker compose up -d postgres payswift
docker compose build worker
docker compose run --rm worker python -m alembic upgrade head
docker compose up -d worker
```

The worker does not apply migrations automatically. It waits for PostgreSQL readiness through Compose, connects to postgres and payswift by service name, and retries failed loop iterations. The existing PaySwift service definition and files are unchanged. SIGINT/SIGTERM stop polling and allow the current bounded HTTP request to finish. SIGKILL recovery uses the durable lease.

Optional sandbox verification deliberately submits one ₹25 payout for a unique synthetic rider in the local PaySwift sandbox. PostgreSQL state exists only in the disposable test database. The sandbox retains that synthetic ledger entry until restarted; the test never resets a shared provider ledger. Do not run another worker against this disposable database while testing.

```bash
curl http://127.0.0.1:8081/health
cd backend
QUICKDROP_RUN_SANDBOX_TEST=1 PAYSWIFT_BASE_URL=http://127.0.0.1:8081 \
  uv run pytest tests/test_payment_sandbox.py -q
```

This test refuses non-loopback URLs and ports other than 8081. It checks health, creates source/dispute evidence, authorizes a complete verified balance, runs the worker, queries the real ledger, checks the PostgreSQL provider ID/status, reconciles again, and checks that no job remains due. It respects retry scheduling and has a 120-second budget. Provider chaos can produce NEEDS_REVIEW or exhaust that budget; inspect traces instead of resending money or clearing reservations.

## Configuration

- PAYSWIFT_BASE_URL: defaults to http://localhost:8081 locally; Compose uses http://payswift:8081.
- PAYMENT_POLL_SECONDS: idle poll delay, default 2, range 0.1–60 seconds.
- PAYMENT_MAX_ATTEMPTS: automatic job-attempt budget, default 8, range 1–20.
- Existing PostgreSQL settings remain in use. Ops reconciliation now requires a server session; see [Ops authentication](ops.md).

httpx is promoted from a development dependency to a runtime dependency through uv. The lock retains existing package versions. requirements.txt is regenerated from the lock.

## Authorization and accounting

`authorize_payment(factory, client, dispute_id, request, source_data_complete=...)` is a server-side service, not a route. Its caller must supply the trusted vendor rider identity, the original complaint timestamp, and an ingestion-aware coverage assertion. It must never accept an LLM's amount, client-provided approval flag, or chat-mentioned rider ID as authority.

The service fetches the rider-scoped provider ledger outside a transaction, then locks the rider and dispute. It requires VERIFIED/AWAITING_APPROVAL dispute status, a verified amount, nonempty unique item scope, and fresh deterministic reconciliation against real trip/payout records. Stored item amounts and scope must match the engine. The entire verified outstanding balance must be positive whole rupees. Existing intents for a dispute are returned without creating or reviving another obligation, including FAILED/UNKNOWN intents.

The full balance is reserved; no amount parameter permits partial payments. Any dispute with verified amount above ₹200 requires Ops approval, even if prior adjustments reduce its remaining balance below ₹200. A daily AUTO reservation, an observed AUTO payout on the same IST day, or an older in-flight AUTO request also requires Ops review. The database's existing unique AUTO rider/day index remains the final concurrent reservation barrier across every status. The reservation date is the authorization date in IST; the worker refuses an unsent AUTO payment after that date. Provider-confirmed transfers that cross midnight also consume the observed day conservatively.

Pending approval queue entries are created once under the rider/dispute locks, always for the full outstanding balance. A changed pending approval amount blocks authorization. A later Ops workflow may persist an APPROVED queue row with matching full amount, assigned operator, and resolution timestamp; only that database evidence permits OPS_APPROVED intents. No approval/rejection mutation endpoint is implemented here. Rejected/resolved decisions do not silently restart authorization. Balances above the provider's ₹10,000 single-request limit are escalated without splitting.

The persisted authorization contains the original claim request, verified timestamp, exact amount, source evidence, per-source allocations, and approval ID when applicable. The idempotency key is stable per dispute; the provider reference is quickdrop:<intent UUID>. Unknown payments block the same discrepancy through existing financial-engine prior-claim guards. Unattributed provider ledger entries, conflicting correlation, missing allocation evidence, and previously confirmed local payouts missing from the ledger block new authorization.

Before POST, the worker performs another ledger GET and recomputes current source balances, excluding only its own already-reserved intent from prior-payment blockers. Newly imported historical credits, changed balances, ineligible data, revoked/invalid evidence, or other obligations block dispatch. It never increases or reduces an authorized amount silently. Trusted ingestion and mutation code must continue to preserve financial sources after reservation; the existing controlled synchronization guard protects decision history. No transaction can make a provider's external ledger and PostgreSQL globally atomic.

## Provider client

PaySwiftClient reuses httpx.AsyncClient connections and performs one HTTP attempt per method. Redirects and proxy environment configuration are disabled. Connection/pool timeouts are two seconds; the httpx operation timeout is five seconds with a seven-second total request budget. No hidden HTTP retry loop exists.

The actual supplied sandbox ledger shape is `{data:[...],count:n}`. Every entry must have payout_id, rider_id, integer amount, reference, status=processed, and an aware created_at timestamp. The read-only provider bytecode metadata confirms these fields; the compiled service is not executed or modified during implementation. A validated 201 must also match the intended rider, amount, and reference. Payout IDs must be nonempty provider-formatted identifiers. Ledger count, ownership, conflicting identifiers, and multiple correlated payouts are checked.

Only 400 is a terminal provider validation rejection. A 429 is known not to have accepted the request in this sandbox contract and may schedule the same body/reference/key again. Retry-After accepts seconds or an HTTP date. Backoff uses exponential delay with jitter, capped at 300 seconds before applying Retry-After. A provider delay above one day goes to review rather than retrying sooner than requested. Transient ledger unavailability before POST can also safely defer an unsent request. Timeouts, connection failures, lost/invalid 201 bodies, 409, 5xx, and unexpected statuses remain potentially ambiguous.

## Outbox state machine and fencing

payment_intents is the only durable queue. No additional table or broker is introduced.

- PENDING: authorized, unsent, or safely scheduled after a 429/preflight deferral.
- PROCESSING: a claimed POST or GET attempt with a 60-second lease and random ownership token.
- SUCCEEDED: a validated 201 or a ledger entry matching rider, reference, amount, and any known provider ID.
- UNKNOWN: an attempted POST or expired lease whose outcome is not yet established. Automatic work here performs GET only.
- FAILED: a definite 400; no automatic retry.
- NEEDS_REVIEW: conflicting evidence, invalid/stale authorization, day rollover, or exhausted automatic budget.
- AWAITING_APPROVAL remains compatible with existing schema; new approval requests use ops_queue without creating an executable intent.

Claiming uses FOR UPDATE SKIP LOCKED. It commits ownership and increments the existing retry_count before HTTP. retry_count counts claimed worker attempts, including reconciliation and explicit manual attempts, not just POSTs. next_retry_at schedules future work. post_started_at is committed before a possible POST, so a crash before sending is conservatively indistinguishable from a crash after sending. Only a definitive 429 or a known unsent preflight deferral clears this marker for another POST. Crash recovery never clears it merely because GET returns an empty ledger.

No database transaction stays open during provider HTTP. Completion locks the row and checks the processing token; a stale worker cannot overwrite a recovered owner's state. Confirmed payment updates, dispute completion, and audit events commit together. A conversation resolves only when no other unresolved dispute remains. No rider message claiming success is fabricated. A provider ID already attributed to another intent causes review.

Ambiguous POSTs persist UNKNOWN and schedule reconciliation. Matching GET evidence marks SUCCEEDED. Missing GET evidence remains UNKNOWN and eventually NEEDS_REVIEW. No path from UNKNOWN performs POST. A last-budget ambiguous POST requires explicit manual GET review because automatic attempts are exhausted. Known successful transfers remain SUCCEEDED even if a later sandbox restart erases the ledger; the missing evidence is recorded in a trace and blocks new authorization. No reservation is released by a failure or provider restart.

## Internal API

Existing GET /ui/ops/payouts and GET /ui/ops/payouts/{id} remain. POST /ui/ops/payouts/{id}/reconcile claims a GET-only attempt and returns the existing payout response. It returns 404 for an unknown intent and 409 while another owner holds the lease. It never executes POST /v1/payouts, creates a payment intent, or authorizes an adjustment. Reconciling an unsent PENDING intent leaves it PENDING when no entry exists; the independently running worker can still execute its previously authorized job later.

All routes retain the server-side local development guard: APP_ENV=development, ENABLE_LOCAL_INTERNAL_READS=true, and loopback client. CORS now allows POST for the guarded action. Provider client pools close during API shutdown. Real session authentication and authenticated vendor ingress remain future work.

Ops metrics count confirmed intents with provider identity and either a durable dispatch marker or a ledger reconciliation timestamp. This represents recorded provider evidence, not a new independent provider lookup on every dashboard request.

## Audit and limitations

Existing agent_traces stores authorization decisions, scoped ledger lookups, request starts, sanitized outcomes, scheduling, and budget/review errors. Amounts use exact Decimal strings in structured payloads. Raw HTTP bodies, exception text, credentials, hidden reasoning, and lease tokens are not logged. Trace events distinguish claimed work from a validated outcome; a crash may leave only the start event.

PaySwift has no durable ledger epoch or restart proof. An empty response cannot prove an ambiguous payout never happened. Missing or unattributed history therefore requires review. Initial authorization assumes this application is the sole adjustment writer and its durable database has not been lost; an entirely erased external ledger plus erased application history cannot be reconstructed. Restore durable backups and obtain independent provider evidence before enabling payments after such a loss.

Processing is at most one sequential job per worker process; multiple processes can claim different rows safely. Automatic retries are bounded; review requires human operations in a later milestone. Database outage or abrupt shutdown can defer completion until lease recovery. Existing legacy intents without authorization evidence are never dispatched; they require review. Existing legacy source allocations cannot be guessed. No automatic backfill, database reset, payment splitting, or cross-provider fallback occurs.

## Migration and changed files

Revision 20af73f418ab follows 7d2f6419bc30. It adds nullable authorization JSONB, processing_token UUID, and post_started_at aware datetime to payment_intents. Existing status constraints, daily reservation index, data, and migration history remain intact. No new tables or destructive upgrades are added.

For rollback, stop every worker and payment writer first. Resolve/export all uncertain jobs and preserve authorization/lease evidence in a backup. Prefer a forward fix once payment traffic exists. Only then may a developer downgrade to 7d2f6419bc30; this drops the three metadata columns but keeps intents and daily reservations. Old code must not execute new pending jobs after metadata removal.

New files:

- app/integrations/__init__.py and payswift.py.
- app/services/payment_authorization.py, payment_reconciliation.py, payment_types.py, payment_worker.py.
- app/repositories/payment_jobs.py.
- app/workers/__init__.py and main.py.
- alembic/versions/20af73f418ab_payment_worker_metadata.py.
- Dockerfile, .dockerignore, and docs/payments.md.
- tests/test_payswift.py, test_payments_database.py, and test_payment_sandbox.py.

Updated files: app/core/config.py, app/models/payment_intent.py, app/api/ui/ops.py, app/repositories/ops.py, app/main.py, .env.example, pyproject.toml, uv.lock, requirements.txt, README.md, docs/core-apis.md, and repository docker-compose.yml. Frontend, CSVs, financial-engine implementation, prior migrations, and payswift/ remain unchanged.
