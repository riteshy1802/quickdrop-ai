# Final remediation: D01–D09

Observed 29–30 October 2026. Branch: `fix/submission-readiness`. No push or deployment.

**Verdict: PARTIAL submission readiness.** All nine defects received scoped remediation;
D05 remains partial because variable model latency can still exceed the foreground
budget and the assignment supplies no outbound messaging transport. The portable
full-deployment evaluator also exposed genuine uncertain PaySwift executions. These
are failures, not successful payments or a reason to weaken duplicate-payment guards.

## Provenance and preservation

- Starting SHA: `c5bd535bdc045775588213255faa29c38111d6b4`.
- Ending tested implementation SHA: `0c0efff` (full value in `ending-code-sha.txt`).
  Documentation/evidence commits follow this implementation SHA; the branch history
  records their hashes without a self-referential report commit hash.
- `git status --short` was empty before modification. `starting-worktree.txt` was
  captured after creating the evidence directory and therefore lists that directory.
  No preexisting changes were discarded. Logical changes were committed separately.
- Original CSVs, conversation expectations, policy, sandbox bytecode and original
  audit evidence were not rewritten. See `checks/source-preservation.json`.
- No migration/model/financial-engine/payment-worker policy was changed. Normal
  development databases, payment records and Docker volumes were not reset.

## Defect disposition

| ID | Initial finding | Exact change | Regression/verification | Status |
|---|---|---|---|---|
| D01 | Compose omitted the API and startup migration owner | `docker-compose.yml`: API, separate worker sharing build/config, one-shot `migrate`, bounded `provider-ready`, deliberate profiled `seed`, frontend, project-scoped network. `backend/Dockerfile`: API default. `app/scripts/wait_provider.main`: bounded readiness. `frontend/Dockerfile`, `.dockerignore`: reproducible production build excluding secrets. | Fresh disposable project/volumes; migrations head/check; data import; API/provider/frontend/proxy all HTTP 200; Redis/internal provider connectivity; running worker; restart row counts unchanged. | FIXED |
| D02 | URL-taking public evaluator absent | `evals/run.py`: stdlib HTTP client, `submit` bounded same-payload retries, schema checks, original 24 scenarios/30 inputs, trace/Ops/provider evidence, independent decision/authorization/settlement/delivery results, duplicate detection, nonlocal opt-in and JSON output. `evals/test_run.py`, `evals/README.md`; CI runs contract tests. | Seven tests pass, including incomplete and valid HTTP-only servers, nonlocal refusal, duplicate authorization with correct provider amount, original IDs, and retry preservation. Two complete real HTTP evaluations executed; latest 24 decisions pass, 3 provider scenarios fail honestly. | FIXED |
| D03 | Raw development conversations missing | `ai-logs/development/*.jsonl`, `provenance.json`, `ai-logs/README.md`: authentic Codex session metadata and chronological raw user/assistant message records from this repository. Original files unchanged; no reconstructed content. Tool payloads, hidden reasoning and telemetry excluded from conversation exports. | 14 sessions, 1,859 valid JSONL records; source/export hashes and redaction provenance; zero current known credential or recognizable AWS/Groq key matches. | FIXED |
| D04 | Generic earnings + trip counts skipped daily bonus | `app/agent/nodes.expand_investigation_scope`, `Nodes.understand`; extraction prompt v8; `tests/test_incentive_scope.py`. Day-scoped PAYOUT with count/target evidence also investigates incentive; named trip-only scope remains narrow. No inferred entitlement from claimed counts. | Seven new backend regressions; original R005 resolves kal against original timestamp to 21 September, verifies ₹150, creates one automatic intent and confirms isolated provider payment. R025 and R009 remain zero. | FIXED |
| D05 | Final answer replaced by acknowledgment on slow turns | `app/core/config.Settings.agent_foreground_seconds`: measured 5.5→7 seconds, maximum 7, within unchanged 8-second webhook budget and approximately 10-second vendor deadline. `backend/docs/agent.md`: delivery limitation. Existing single extraction call, deterministic final renderer and durable recovery retained. | Isolated real Nova rerun: 28/30 final original responses, up from 21/30; two acknowledgments (scenarios 3,17). Independent full Compose run: 30/30 original finals, max 5.7868s. Variable delivery remains demonstrated; no fictional outbound transport added. | PARTIAL |
| D06 | Stub root README | Root `README.md`: setup, actual architecture/tools, human approval, worker/provider reconciliation, SSE, environment, contracts, evaluator, measured results and limitations. | Referenced commands/files exist; Docker and production build exercised; links resolve. Isolated and full-deployment results are distinguished. | FIXED |
| D07 | Financial approvals offered unsupported assignment | `components/ops/approvals.tsx`: assignment available only for escalations in queue and case review. Backend assignment rules unchanged. | Component regression confirms hidden on approvals and present on escalations; server workflow suites remain green. | FIXED |
| D08 | Empty checks incorrectly implied verification | `CaseReview`: explicit unavailable text for empty checks; no empty `every()` success; failed checks block UI approval. Unknown/unavailable evidence never claims validation. `lib/api/ops.ts`: documents absent public checklist fields. Backend still revalidates every approval. | Seven Ops tests cover approval/escalation actions, empty/missing evidence, passed/failed/unknown checks and closed state. Existing `CaseResponse` exposes no actual checklist, so none was fabricated. | FIXED |
| D09 | Root configuration absent | Root `.env.example`, aligned backend example, root README and Compose container overrides; host frontend example retained. AWS/Nova or Groq, DB, Redis, PaySwift, Ops credentials, URLs and optional historical clock documented. | Host/container connections exercised. No actual `.env` or credentials committed. | FIXED |

## Executed checks

Full outputs live in `checks/`; original audit outputs remain in `../final-audit/`.

| Command/check | Observed result |
|---|---|
| `uv run --directory backend pytest -q` | 494 passed, 1 skipped, 233.14s. Session fixture creates/drops disposable PostgreSQL databases and validates upgrade/downgrade/schema. |
| `uv run --directory backend ruff check .` | Passed. |
| `uv run --directory backend ruff format --check .` | 158 files already formatted. |
| Ruff lint/format of standalone evaluator/tests | Passed. |
| `python -m unittest discover -s evals -p test_run.py` | Seven passed. |
| `npm test` in frontend | 33 passed. |
| `npm run lint`, `npm run typecheck`, `npm run build` | All passed. |
| Workflow YAML parsing | Valid; current three CI jobs retained; portable HTTP contract tests added. |
| `docker compose config --services` | API, worker, frontend, migration, provider readiness, Postgres, Redis, unchanged PaySwift. Seed available deliberately under setup profile. |
| Disposable `docker compose ... up --build -d` | Clean stack starts; migration/readiness complete before API/worker; frontend waits for healthy API. |
| Deployed Alembic `current`, `heads`, `check` | Single head `ef5a812c731a`; no new upgrade operations. |
| HTTP health | API, provider, frontend Rider page and frontend API proxy all 200. |
| Internal connectivity | Redis ping succeeds; API can read provider health and PostgreSQL. |
| Deliberate CSV seed | 40 riders, 3,304 trips, 3,222 payout lines. Ten identical source trip duplicates skipped; original CSVs untouched. |
| Restart persistence | 40 riders, 3,304 trips, 3,222 payout lines, 10 then-existing payment intents retained across Postgres/API/worker restart. |

The one pytest skip is the explicitly gated `test_real_sandbox_round_trip` requiring
`QUICKDROP_RUN_SANDBOX_TEST=1` and port 8081. It was not pointed at the developer's
shared provider. Actual sandbox execution was exercised extensively in isolated live
and disposable Compose runs instead; the skipped test is not counted as passing.

## Live Nova and actual payments — separate modes

### Fresh database and provider per scenario

Command:

```sh
AUDIT_REPORT_DIR="$PWD/evals/reports/final-remediation/live" \
AUDIT_LOG_DIR="$PWD/ai-logs/final-remediation" \
AGENT_FOREGROUND_SECONDS=7 LLM_PROVIDER=amazon \
uv run --directory backend python ../evals/audit_live.py
```

Original 24 scenarios, original 30 rider inputs/IDs/timestamps, real Nova Pro
`us.amazon.nova-pro-v1:0`, prompt v8. Each case used fresh PostgreSQL and unchanged
PaySwift; Redis was separately isolated. No fake model labels were substituted.

- Financial decisions: **24/24 PASS**.
- Expected provider outcome: **24/24 PASS**, including expected zero-transfer cases.
- Actual automatic intents: **11**, all provider-correlated, totaling **₹664**.
- Authenticated R016 human approval: exactly one **₹425** intent and provider-confirmed
  payment; repeated approval refused. R034 rejection: no payment, repeated rejection refused.
- Original-request final answers: **28/30 turns**, **22/24 scenarios**. Two acknowledgments
  later completed through durable recovery, not through an outbound vendor sender.
- Maximum original HTTP latency: **7.0663s**. Maximum eventual completion: **17.0901s**.
- LLM: 29 invocations, 27 validated outputs, two foreground cancellations, no extraction
  unavailable errors. Median validated extraction: **1.9501s**. Median measured non-LLM
  request overhead: **0.2206s**. One sequential model extraction per fresh turn; zero
  sequential final-generation calls. These are wrapper/HTTP measurements, not SQL spans.
- See `live/live-24-results.json`, `live/ops-R016.json`, `live/ops-R034.json`,
  `checks/webhook-latency.json` and `ai-logs/final-remediation/`.

### Full Compose deployment, one shared disposable sandbox

Command:

```sh
python evals/run.py http://localhost:18000 \
  --payswift-url http://localhost:18081 \
  --output evals/reports/final-remediation/portable-24-results.json
```

The published interface remains `python evals/run.py http://localhost:8000`.
Separate host ports prevented conflicts with the developer's running services.
The evaluator uses only public HTTP APIs; the internal audit is not substituted for it.

Latest full deployment run:

- Decisions **24/24 PASS**.
- Financial authorization **21 PASS, 3 NOT APPLICABLE** (verified no-payment safety or
  clarification cases). NOT APPLICABLE is not a claim that an approval occurred.
- Final answers in original HTTP requests **30/30**, max **5.7868s**. This individual
  successful timing run does not erase the isolated run's two delayed responses.
- Provider verification **21/24 PASS**, **3 FAIL**. Overall **21/24 PASS**, nonzero exit.
- R003: verified/authorized ₹25 but no confirmed provider payout. This one unresolved
  obligation affects both scenarios 1 and 5; no duplicate intent was issued.
- R035: verified/authorized ₹25 but no confirmed provider payout (scenario 21).
- Trace evidence records provider HTTP 503 followed by uncertain status/ledger checks.
  Existing worker safeguards retained the reservation and avoided an unsafe resend.
  Exact captured states are in `checks/portable-final-db-state.json` and
  `portable-unconfirmed-traces.json`; zero in the ledger is not settlement success.

The earlier exploratory full deployment run is also preserved in
`portable-initial-results.json` and `checks/portable-initial.txt`. It exposed uncertain
R007 ₹34 and R026 ₹32 execution, one HTTP 503, one delayed final and three evaluator
misclassifications of no-authorization cases. Evaluator retry/classification defects
were fixed and independently regression-tested. The genuine provider failures were
not suppressed, converted to passing assertions, or repaired by resetting an obligation.
Only the entire disposable test project was reset between independent fresh runs.

**Do not combine isolated successful payments with full-deployment failures into a
single all-green end-to-end claim.** Provider faults vary with sandbox execution.
The safe worker may leave ambiguous execution unresolved; Ops/provider confirmation
is required before asserting payment completion or attempting another obligation.

## Clocks, data and environment

Official scenario `received_at` always takes precedence for eligibility/relative dates.
R005's `kal` therefore resolves to 21 September from its original 22 September event.
Local-only `APP_REFERENCE_TIME` is optional and rejected outside development.
Authentication, audit times, leases, retries and daily authorization reservations keep
real system time. The payment authorization date is the actual current IST day under
existing transactional rider locks, also accounting for provider-confirmed crossings
of midnight; the demo clock cannot reserve a second auto-payment slot.

Container connection overrides use `postgres`, `redis`, `payswift`. Host examples use
localhost. Credentials were supplied through existing ignored environment files;
no secret-bearing `docker compose config` output was saved. Supplied PaySwift service
configuration and bytecode are unchanged. Raw AI exports retain genuine conversations
with explicit redaction and export scope, not audit traces masquerading as sessions.

## Remaining submission tasks

1. Resolve D05's remaining delivery limitation, or explicitly submit it as a known
   limitation. A vendor outbound API is not provided; SSE is not a vendor transport.
2. Investigate ambiguous provider executions through existing reconciliation/Ops
   records. Do not assume that a correct decision or local reservation means payment.
   Do not run these financial evals against shared development or production state.
3. Review redacted session exports before granting repository collaborator access.
4. Merge the reviewed remediation branch to `main`, run GitHub CI there, add the required
   assignment collaborator and submit the private repository link before the deadline.
   No push, collaborator change or deployment was performed by this remediation.

Cleanup and preservation verification is recorded in `checks/cleanup.json`.
