# QuickDrop backend

Python 3.12, FastAPI, SQLAlchemy 2, asyncpg, Alembic and Pydantic Settings. Dependencies are
managed by **uv** and pinned in `uv.lock`. `requirements.txt` is an exported
compatibility file, not the dependency source of truth.

From `backend/`:

```sh
uv sync --locked
uv run alembic upgrade head
uv run alembic current
uv run alembic heads
uv run alembic check
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal, run `curl http://localhost:8000/health`. Verification:

```sh
uv run pytest -q
uv run ruff check app alembic tests
```

PostgreSQL must already be running (`docker compose up -d postgres` from the
repository root). Settings read the existing root `.env`, then optional
`backend/.env`; process environment variables take precedence. Existing
`POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` work directly. Host defaults
to `localhost:5432`. Set `POSTGRES_HOST=postgres` for a future Compose backend.
Alternatively, supply `DATABASE_URL`; URL passwords must be percent-encoded.
Individual `POSTGRES_*` settings handle reserved password characters automatically.
No real credentials belong in source control or `alembic.ini`.

## Structure

- `app/core/config.py`: centralized settings and safe connection URL construction.
- `app/core/database.py`: lazy pooled async engine, session factory and session
  dependency. Callers explicitly commit; failures roll back and sessions close.
- `app/models/`: one shared declarative Base and eleven model modules. Importing
  `app.models` registers all tables; relationships avoid implicit async I/O.
- `alembic/`: schema migrations; the initial revision is `078eb21553bb`.
- `tests/`: metadata and actual PostgreSQL constraint/concurrency checks.
- `app/main.py` and `app/api/`: async FastAPI app, readiness and read-only routers.
- `app/repositories/`: rider, trip and historical payout queries, with no policy calculations.
- `app/schemas/`: Pydantic v2 ORM response schemas; decimals serialize as exact strings.
- `app/scripts/seed.py`: validated, transactional and idempotent CSV import.

Tables: `riders`, `trips`, `payout_lines`, `ops_users`, `conversations`, `messages`,
`disputes`, `dispute_items`, `payment_intents`, `ops_queue`, `agent_traces`.
Alembic maintains a separate `alembic_version` tracking table.

## Database guarantees

Money and distances use exact `NUMERIC`, never floating point. Payment amounts
must be finite, positive whole rupees. AUTO payments are capped at ₹200;
OPS_APPROVED payments can exceed that amount. Unconstrained numeric scale is
intentional: fractional inputs reach the check constraint instead of being
silently rounded before validation.

The partial unique index `uq_payment_intents_auto_rider_day` reserves one AUTO
payment per rider and explicit IST business date, across **all** statuses,
including FAILED and UNKNOWN. Retry/reconciliation must reuse the same intent
and idempotency key. No status change releases a reservation. Future payment
services must compute the IST date explicitly; do not cast a UTC timestamp to a
date. The policy engine must still enforce eligibility, verified shortfalls,
approval authorization and total payment limits; schema constraints do not
replace that logic.

Composite foreign keys enforce rider ownership of trip payouts, conversation
claims and payment intents. RESTRICT deletes preserve referenced history;
historical payout rows must remain source records rather than being rewritten
for new payments. Foreign keys are indexed, alongside conversation chronology,
pending Ops work, retries and leases. Nullable unique webhook IDs allow multiple
outbound messages while deduplicating incoming deliveries; replies can be cached.
Only OPS messages may be private internal notes.

Structured state uses JSONB with independent empty-object defaults. Timestamps
are timezone-aware and connections use UTC. `updated_at` has an initial database
default and SQLAlchemy on-update behavior; future raw SQL updates must set it
explicitly. ORM trace writes redact sensitive payload keys recursively; future
trace writers must also sanitize free-text values and avoid raw inserts that
bypass validation. Store public decisions, never private hidden reasoning.

## Migrations and tests

Generate future revisions with `uv run alembic revision --autogenerate -m "..."`,
review the generated SQL and constraints, then upgrade. Application startup must
never call `create_all()` or stamp over unapplied changes.

Tests create a unique `quickdrop_test_<uuid>` database using the configured
PostgreSQL server/user, migrate it, run checks, exercise downgrade/re-upgrade, and
drop only that generated database. The test role needs CREATEDB. Development
tables are never cleared or downgraded. Concurrent reservation tests use separate
connections and overlapping transactions.

To refresh the compatibility export after a dependency update:

```sh
uv export --locked --no-dev --format requirements-txt --output-file requirements.txt
```

## CSV imports

`uv run python -m app.scripts.seed` resolves the root `data/` directory from the
module location. From any shell directory you may also use
`uv run --directory /absolute/path/to/quickdrop-ai/backend python -m app.scripts.seed`.
Use `--data-dir /path/to/csvs` to select an explicit dataset directory.

The assignment exports have **40 riders, 3,314 trip rows and 3,222 payout lines**.
Ten trip rows are identical duplicates, so a fresh import inserts 3,304 unique
trips. The user approved exactly two rider-reference corrections: `R7 -> R007`
(38 rows) and `r19 -> R019` (26 rows). The deterministic normalization function
requires the canonical rider to exist in `riders.csv`, rejects ambiguity and
unknown IDs, and logs each transformed reference with its source file and row.
It never changes trip IDs or the original CSV files. Conflicting duplicate IDs
and missing/wrong-owner trip references fail validation.

All three imports share one transaction, ordered riders, trips, payout lines.
`ON CONFLICT DO NOTHING` targets the source primary key. Repeating the command
inserts zero records and reports skipped rows; existing records are never
updated. Failures roll back all inserts and exit nonzero. Summary counts print
as JSON after commit; transformation logs go to stderr. Historical negative
penalties and nullable incentive trip references are preserved.

## HTTP API

- `GET /health`: checks PostgreSQL with a three-second timeout, returning 200
  with `{"status":"healthy","database":"connected"}` or 503 on failure.
- `GET /ui/riders`: paginated riders.
- `GET /ui/riders/{rider_id}`: rider detail, or 404.
- `GET /ui/riders/{rider_id}/trips`: optional `date_from`, `date_to`, `status`.
- `GET /ui/riders/{rider_id}/payout-lines`: optional `date_from`, `date_to`,
  `line_type`, `trip_id`.

Collections return `{items,total,limit,offset}`. Default limit is 50, maximum
100; offset starts at zero. Date bounds are inclusive IST calendar dates. Trip
queries translate them to half-open timezone-aware UTC timestamp ranges, and
payout queries compare source calendar dates. Ordering includes stable source
IDs. Error responses use `{error:{code,message,details?}}` and omit database
credentials and internal exception details. Decimal values serialize as strings.

CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`. Override
`CORS_ORIGINS` with a JSON string array if needed. `/docs` exposes the API schema.
These `/ui` endpoints are read-only development APIs. API startup neither seeds
data nor runs migrations; shutdown disposes the initialized async connection
pool. The session dependency closes sessions and rolls back failures; callers
own commits.

Admin seeding, authentication, policy calculations, agents, PaySwift execution,
workers and the assignment's `/messages`, `/trace/{rider_id}` and `/ops/pending`
endpoints are deferred. Compose's API service and `evals/run.py` are also future
work; start this milestone's API with the Uvicorn command above.

## Continuous integration

`.github/workflows/workflow.yml` runs on pushes to `main`, pull requests into
`main`, and manual dispatch. The backend quality job runs Ruff and
`uv run pytest -q -m 'not database'` without a database. The PostgreSQL job uses
an isolated PostgreSQL 16 service, applies migrations, verifies the current head
and schema consistency, and runs `uv run pytest -q -m database`. Existing test
assertions are shared with local runs; the `database` marker only selects them.
Generated Alembic revision files and virtual environments are excluded from Ruff;
Alembic's environment and application/test code remain checked. The frontend job
uses Node.js 22, `npm ci`, lint, type checking and the production build.

The workflow includes a commented full-application evaluation scaffold. Enable
it only after FastAPI, its Compose service and `evals/run.py` are implemented,
including their dependency/environment and data setup. No deployment runs in CI.
