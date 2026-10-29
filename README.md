# QuickDrop AI

Rider payout support in English, Hindi and Hinglish, with an Ops console. LangGraph
uses Nova Pro (or Groq) for request understanding and general education; deterministic
tools verify trusted rider identity, source records and policy. Model text cannot
move money. [Policy](docs/policy.md) · [Agent design](backend/docs/agent.md).

**Run:** copy `.env.example` to `.env`, set `POSTGRES_PASSWORD`, your Bedrock credentials
(or Groq key), and `OPS_ADMIN_EMAIL`/`OPS_ADMIN_PASSWORD`. Run:

```sh
docker compose build api frontend
docker compose run --rm --no-deps api python -m app.scripts.check_env
docker compose up --build -d
docker compose run --rm seed
docker compose run --rm api python -m app.scripts.seed_admin
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
```

Examples contain placeholders, not credentials. Never commit `.env`. Compose loads
root `.env`, then optional `backend/.env`; the latter overrides duplicate values.
Container database, Redis and PaySwift destinations are explicitly set by Compose.
Set a shared 32+ character `DEMO_SESSION_SECRET` so Rider cookies survive API restarts. Missing
optional variables are reported without failing validation; the selected model,
database and administrator settings must be configured. AWS credentials need Bedrock
InvokeModel access to the configured inference profile. Temporary credentials also
need `AWS_SESSION_TOKEN`. Alternatively select Groq and set `GROQ_API_KEY`.
For independent local projects, set `COMPOSE_PROJECT_NAME` and the five `*_HOST_PORT`
variables; database and Redis volumes then belong to that project. Ports bind to
loopback; public access requires an explicitly configured reverse proxy.
`BACKEND_URL` is baked into Next.js rewrites during image build; Compose uses
`http://api:8000`. Rebuild if changing that destination. Server keys must never use
a `NEXT_PUBLIC_` prefix. [Docker verification](docs/DOCKER_VERIFICATION.md).

Open http://localhost:3000/rider or http://localhost:3000/ops. API health is
http://localhost:8000/health. Compose starts Postgres, Redis, unchanged PaySwift,
a single-owner Alembic migration step, API, separate durable worker and frontend.
Seeding is deliberate and idempotent; persistent volumes are never reset at startup.
Backend Docker connections use `postgres`, `redis`, `payswift`; host commands use
localhost. Host development: `make backend`, `make workers`, `make frontend`.
The frontend proxies `/api/backend` to `BACKEND_URL` (Docker: `http://api:8000`).

**Money:** completed fare is ₹25 + ₹6/km after 2 km, multiplied by surge and rounded
half-up per trip; 12 completed trips/day earn ₹150; rider cancellations cost ₹10.
Only the last seven IST days qualify. Auto-pay is at most ₹200/dispute and once per
rider/day; larger or repeat claims require Ops approval. Transactional reservations,
provider reconciliation and idempotent payment intents protect against duplicates.
The separate worker sends PaySwift requests and handles uncertain outcomes before
retrying. Authorization is distinct from provider-confirmed settlement. PaySwift is
a sandbox: no real bank transfers. Ops can approve/reject, take over, reply, add
private notes and resolve cases; Redis Pub/Sub and SSE deliver UI updates.

**API:** `POST /messages` accepts `message_id`, trusted `rider_id`, `text`, and an
ISO timezone-aware `received_at`, returning `{"reply":"..."}`. Reuse the exact payload
for retries. `GET /trace/R003` gives ordered steps; `GET /ops/pending` lists approvals
and escalations. See [contracts](SUBMISSION.md). Historical evaluator timestamps
always win; optional development-only `APP_REFERENCE_TIME` affects interactive demos,
never audit/authentication/worker clocks or the real-date daily authorization guard.

**Evaluate only fresh isolated sandbox state** (the command creates financial side effects):

```sh
python evals/run.py http://localhost:8000
```

The evaluator uses public HTTP APIs and the PaySwift ledger (default localhost:8081,
configurable with `--payswift-url`); writes `evals/results.json`; reports decision,
authorization, provider payment and initial delivery separately. Nonlocal targets
require explicit `--allow-nonlocal`. Never run on production or shared development data.
Use `--scenario N` with a fresh deployment to isolate a single scenario.

**Verified remediation:** 494 backend tests passed (1 skipped), 33 frontend tests
passed; lint, types and production build passed. Isolated real Nova: 24/24 decisions and
provider outcomes passed; 11 auto payouts totaling ₹664, plus an Ops-approved ₹425
payout. Original webhook final delivery: 28/30 requests (22/24 scenarios); two
acknowledgments completed later. A separate full Compose HTTP run passed 24/24
decisions and delivered 30/30 final replies, but provider verification failed for
three scenarios (two unresolved payments after PaySwift 503s). There is no supplied
outbound transport for delayed vendor replies; readiness remains partial. [Full evidence and remaining limitations](evals/reports/final-remediation/REMEDIATION_REPORT.md).
[Authentic redacted AI sessions](ai-logs/README.md) are included; original audit evidence
is preserved separately. No deployment or real-money payment is performed by CI.
