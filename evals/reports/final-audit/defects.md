# Submission defects

No product fixes were applied during this audit. Every observed failure is retained; original expectations and source data were not changed.

## D01 — P0: Compose does not start the required API

Reproduction/evidence: Run docker compose config --services; there is no API service or port 8000. backend/Dockerfile defaults to worker. A clean full application cannot satisfy the required one-command startup.

Location: `docker-compose.yml; backend/Dockerfile`.

Recommended fix: Add explicit API startup and database initialization ordering, then test clean Compose startup in a disposable project. Preserve supplied payswift service.

## D02 — P0: Portable assignment evaluator missing

Reproduction/evidence: python evals/run.py http://localhost:8000 exits 2. Internal audit harness imports backend and cannot be run against other implementations.

Location: `evals/run.py (absent); checks/portable-evaluator.txt`.

Recommended fix: Implement the separately required URL-taking black-box evaluator using only /messages, /trace, /ops/pending and PaySwift; document one command.

## D03 — P0: Required raw AI development-session exports absent

Reproduction/evidence: Before audit ai-logs contained only README.md. Audit LLM extracts are evidence, not raw exports of development assistant sessions.

Location: `ai-logs/README.md; SUBMISSION.md`.

Recommended fix: Export the actual development sessions, review/redact secrets as required, and document export provenance. Do not substitute summaries or audit traces.

## D04 — P1: Live R005 misses the ₹150 incentive

Reproduction/evidence: Replay original kal ka payout kam aaya hai. 12 se zyada order kiye the maine. Real Nova extracts PAYOUT only. Trip-fare reconciliation returns no shortfall; no intent or provider payout. Expected ₹150.

Location: `backend/app/agent/prompts.py: complaint kinds; backend/app/agent/nodes.py; scenario-06-R005.json`.

Recommended fix: Investigate applicable daily bonus evidence when an earnings complaint plus trip-count context suggests incentive eligibility; do not guess money from claimed counts. Retain original scenario expectations and add a live regression.

## D05 — P1: Final vendor reply unavailable after successful acknowledgment

Reproduction/evidence: Nine of 30 original HTTP 200 responses were processing acknowledgments. Final answers appear only after durable worker completion and explicit replay/state reads. Vendor stops retrying on 2xx; no outbound final-send integration exists.

Location: `backend/app/services/message_service.py: execute/defer/process; live-24-results.json`.

Recommended fix: Fit useful final decisions within the vendor response budget, or integrate a real outbound final-reply transport and document it. Do not report acknowledgment latency as final-answer latency.

## D06 — P1: Root submission README incomplete

Reproduction/evidence: README.md is the original three-line stub with no setup, agent design, assumptions, eval results or skipped work.

Location: `README.md; BRIEF.md; SUBMISSION.md`.

Recommended fix: Write the required one-page root submission README from measured results, including known failures and exact startup/eval commands.

## D07 — P2: Assign-to-me shown on financial approvals but backend rejects it

Reproduction/evidence: Inspect the shared Assign to me button in CaseReview and ops_case_service.act: assign requires type escalation. Approve directly works; this assignment affordance does not. No browser action was executed in audit.

Location: `frontend/src/components/ops/approvals.tsx: CaseReview; backend/app/services/ops_case_service.py: act`.

Recommended fix: Hide unsupported assignment on approvals or implement compatible assignment rules with endpoint tests.

## D08 — P2: Ops evidence-check panel has no actual check rows

Reproduction/evidence: opsApi.load maps every case to checks: []; CaseReview uses checks.slice(0,6).every, which returns true for an empty list. Server revalidates approval, so this is not proof of unsafe payment authorization.

Location: `frontend/src/lib/api/ops.ts: checks; frontend/src/components/ops/approvals.tsx: eligible`.

Recommended fix: Populate checks from actual persisted evidence or show unavailable explicitly; do not imply all checks passed from an empty array.

## D09 — P2: Root environment/startup documentation incomplete

Reproduction/evidence: Backend/frontend examples exist but root .env.example and root run instructions are absent; Compose requires POSTGRES_PASSWORD.

Location: `backend/.env.example; frontend/.env.example; README.md; docker-compose.yml`.

Recommended fix: Provide a root environment/setup entry point that lists Compose-required values without credentials.
