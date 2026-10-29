# QuickDrop AI

Rider payout support in English, Hindi and Hinglish, with an Ops console. LangGraph
uses Nova Pro (or Groq) for request understanding and general education; deterministic
tools verify trusted rider identity, source records and policy. Model text cannot
move money. [Policy](docs/policy.md) · [Agent design](backend/docs/agent.md).

**Run:** copy `.env.example` to `.env`, set `POSTGRES_PASSWORD`, your Bedrock credentials
(or Groq key), and `OPS_ADMIN_EMAIL`/`OPS_ADMIN_PASSWORD`. Run:

```sh
docker compose up --build -d
docker compose run --rm seed
docker compose run --rm api python -m app.scripts.seed_admin
```

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
passed; lint, types and production build passed. Real Nova: 24/24 decisions and
provider outcomes passed; 11 auto payouts totaling ₹664, plus an Ops-approved ₹425
payout. Original webhook final delivery: 28/30 requests (22/24 scenarios); two
acknowledgments completed later. There is no supplied outbound transport to deliver
those delayed answers to the vendor. [Full evidence and remaining limitations](evals/reports/final-remediation/REMEDIATION_REPORT.md).
[Authentic redacted AI sessions](ai-logs/README.md) are included; original audit evidence
is preserved separately. No deployment or real-money payment is performed by CI.
