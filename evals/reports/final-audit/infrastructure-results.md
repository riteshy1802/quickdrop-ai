# Infrastructure and integration results

## Executed gates

| Gate | Result | Evidence |
|---|---|---|
| Backend pytest | 487 passed, 1 skipped | [log](checks/backend-pytest.txt) |
| Backend Ruff lint | PASS | [log](checks/backend-ruff.txt) |
| Backend Ruff format check | PASS: 156 files formatted | [log](checks/backend-format.txt) |
| Frontend ESLint | PASS | [log](checks/frontend-lint.txt) |
| Frontend tests | PASS: 26 tests | [log](checks/frontend-test.txt) |
| TypeScript/type generation | PASS | [log](checks/frontend-typecheck.txt) |
| Next.js production build | PASS | [log](checks/frontend-build.txt) |
| Audit disposable migrations/seed | PASS | [log](checks/audit-migrations.txt), [counts](seed-counts.json) |
| Existing Postgres/Redis/PaySwift Docker health | PASS | [state](checks/compose-ps.jsonl) |
| Existing API `/health` | HTTP 200; PostgreSQL ready | Checked read-only; all 24 isolated route health calls also 200 |
| Existing local worker | Running | [process roles](checks/local-runtime-processes.json) |
| Complete Compose startup | FAIL by service definition | [declared services](checks/compose-services.txt): no API on 8000, no frontend/migration/seed orchestration |
| Portable assignment evaluator | FAIL: missing file, exit 2 | [command output](checks/portable-evaluator.txt) |
| Workflow syntax/triggers/permissions | PASS | [parsed workflow](checks/workflow-syntax.json) |
| Remote CI execution | NOT TESTED | No push or dispatch performed |
| Private repo/collaborator/deadline | NOT TESTED | Manual submission logistics required |

## Scope and isolation

The live harness exercises actual FastAPI routes through HTTPX ASGITransport, not a separately started audit TCP server. Database session dependencies point only to generated audit databases; no LLM or payment logic is replaced. A fresh unchanged `payswift/server.pyc` process runs on a fresh port per scenario. A separate temporary Redis container prevents audit events reaching the developer's workspace. The supplied Compose sandbox and development DB are not reset or used for audit transfers. Original `received_at` timestamps control eligibility; the demo clock is unset inside the audit process only. Leases, audits, retries and daily reservations retain real system time.

The harness manually invokes existing durable message/payment worker functions and honors stored retry times; it does not accelerate leases or mutate retry timestamps to force success. Settlement was observed for up to 30 seconds after each rider turn, and 45 seconds after authenticated human approval. Each scenario was snapshotted before any extra Ops tests. No production application, prompt, financial policy, CSV, migration or expected scenario output was changed by this audit.

## SSE and frontend proof boundary

`tests/test_realtime.py` exercised real Redis fan-out, commit/rollback publication, authorization, session expiry, generator heartbeat/disconnect/cancellation cleanup, exact completed-message chunks, payment events, public human replies and private Ops notes. Its complete rider/Ops/worker flow used real Redis and HTTP routes but a controlled LLM/provider. Frontend tests used mocked HTTP/EventSource to verify reconnect/refetch and message identity/dedup. The live 24-scenario graph run separately used the real provider and invoked the real LLM in 23 scenarios; the policy guard rejected R037 before extraction. A single browser run spanning all those real components was **NOT TESTED**; Chrome was not opened, as instructed.

Response deltas are transport chunks of a committed, safe final reply; they are not raw hidden reasoning or a guarantee of native model-token streaming. PostgreSQL refetch supplies missing-event recovery. Frontend queries/mutations use TanStack Query. In the observed payment UI, saved status and approval state remain distinct. Two inspected UI gaps remain: approval-case assignment is offered despite the escalation-only backend endpoint, and evidence-check lists are populated as empty arrays.

## Deployment and reproducibility limits

`docker compose config --quiet` passed. Running a new full `docker compose up` against the developer's environment was deliberately avoided: it would start a writer against existing data and cannot establish clean submission startup. Service membership itself proves that the required API is absent. A standalone backend image build was not repeated; the actual clean production startup remains NOT TESTED. Existing migrations were tested in disposable DBs, including upgrade/downgrade/check in the pytest fixture.

The README at repository root is still an assignment stub. Backend/frontend environment examples exist, but root `.env.example` and the root one-page run/design/eval summary are missing. The required portable `evals/run.py` is missing. `evals/audit_live.py` is an internal audit harness using implementation imports and DB access; it is explicitly not claimed as the assignment's cross-implementation evaluator.

## Credential and source preservation checks

A current tracked-tree pattern scan found no tracked `.env`, recognizable AWS access key, Groq key or private-key block. This is **not** a complete Git-history secret audit. No credentials/cookies/session tokens were exported into audit artifacts. Source/bytecode hashes are preserved in [audit-preservation.json](audit-preservation.json). Git commit tested: `7ac75f820a4f67e15e2e0eedffad1bcd9391da16` plus the dirty working tree recorded in [manifest.json](manifest.json); results do not certify an unpushed `main` revision.
