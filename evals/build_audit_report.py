"""Render the final audit from captured evidence; never invent or rerun application results."""

import collections
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/reports/final-audit"
read = lambda name: json.loads((OUT / name).read_text())
data = read("live-24-results.json")
rows = data["results"]
metrics = data["summary"]
manifest = read("manifest.json")
llm = read("llm-metrics.json")
ops = {r: read(f"ops-{r}.json") for r in ["R016", "R034"]}


def write(name, text):
    (OUT / name).write_text(text.strip() + "\n")


def link(path):
    return f"[{path}](../../../{path})"


# Each row is a separate auditable acceptance criterion, not a weighted readiness score.
criteria = [
    (
        "A01",
        "Original message text, IDs, rider IDs, order and received_at preserved",
        "PASS",
        "All 30 request records compared with data/conversations.json; 24 fresh DB clones",
        "data/conversations.json; audit-preservation.json",
    ),
    (
        "A02",
        "Configured real LLM and actual LangGraph; no model labels or fallback",
        "PARTIAL",
        "23 scenarios invoked Nova; R037 was correctly blocked before the model. 38 real invocations, 27 validated responses,9 cancellations,2 unavailable extractions; literal 24-scenario model-invocation coverage is not met",
        "app/agent/llm.py; app/agent/graph.py; ai-logs/final-audit/*-llm.json",
    ),
    (
        "A03",
        "Fresh isolated data and supplied sandbox per scenario",
        "PASS",
        "40 riders, 3,304 trips, 3,222 payout lines seeded once; fresh clone and fresh server.pyc process per scenario; independent Redis",
        "evals/audit_live.py; seed-counts.json",
    ),
    (
        "A04",
        "All 24 official financial decisions correct",
        "FAIL",
        "23/24; R005 missed expected ₹150 incentive",
        "scenario-06-R005.json",
    ),
    (
        "A05",
        "Expected payouts actually confirmed with PaySwift",
        "FAIL",
        "23/24 expected outcomes; R005 issued no intent. All 10 produced AUTO intents confirmed, ₹514 total",
        "live-24-results.json; *-traces.json",
    ),
    (
        "A06",
        "Natural-language scenario facts match targeted required mentions",
        "PASS",
        "Dataset reply_mentions checks passed for all 24; these checks are NOT settlement evidence",
        "live-24-results.json",
    ),
    (
        "A07",
        "Fare base ₹25 + ₹6/km after 2 km, surge on whole fare",
        "PASS",
        "Financial arithmetic unit/DB tests passed; live fare cases including R007/R031/R033",
        "app/services/financial/calculator.py; tests/test_financial.py; checks/backend-pytest.txt",
    ),
    (
        "A08",
        "Per-trip ROUND_HALF_UP rounding",
        "PASS",
        "Decimal arithmetic and explicit rounding tests passed",
        "tests/test_financial.py; app/services/financial/calculator.py",
    ),
    (
        "A09",
        "₹150 incentive for 12 completed trips",
        "PARTIAL",
        "Calculator and labelled scenarios pass; live R024 succeeds but R005 extraction skips bonus scope",
        "tests/test_financial.py; scenario-13-R024.json; scenario-06-R005.json",
    ),
    (
        "A10",
        "₹10 rider cancellation; customer cancellation earns zero",
        "PASS",
        "Financial tests and live penalty cases including R014/R027 passed",
        "app/services/financial/calculator.py; tests/test_financial.py; scenario-09-R014.json",
    ),
    (
        "A11",
        "IST day grouping and seven completed-day eligibility",
        "PASS",
        "Clock/eligibility tests passed; original September timestamps used; R022 remains ineligible",
        "tests/test_reference_clock.py; tests/test_financial.py; scenario-12-R022.json",
    ),
    (
        "A12",
        "Business demo clock cannot override official evaluator timestamps",
        "PASS",
        "Audit process cleared demo clock, preserved received_at, and verified input timestamps; clock tests passed",
        "app/core/clock.py; tests/test_reference_clock.py; audit-preservation.json",
    ),
    (
        "A13",
        "Real time retained for audit, retries, leases and auto-pay date",
        "PASS",
        "Stored traces are October, request eligibility September; real daily reservation tests passed",
        "app/services/payment_authorization.py; app/repositories/payment_jobs.py; *-traces.json",
    ),
    (
        "A14",
        "Historical payouts, duplicate source rows and normalization handled",
        "PASS",
        "Seed skipped 10 duplicate trip rows, logged 64 reference mappings; normalization/data-quality suites passed; source hashes unchanged",
        "seed-counts.json; tests/test_data_quality.py; tests/test_normalization_pipeline.py; audit-preservation.json",
    ),
    (
        "A15",
        "No money beyond verified outstanding; current evidence rechecked before POST",
        "PASS",
        "All live intents within verified disputes; overpayment/changed-credit/overlap tests passed",
        "tests/test_payments_database.py; live-24-results.json",
    ),
    (
        "A16",
        "Automatic amount limited to ₹200 per dispute; no splitting",
        "PASS",
        "R016 ₹425 and R034 ₹249 approval, no pre-approval intents; threshold/splitting tests passed",
        "app/services/payment_authorization.py; scenario-10-R016.json; scenario-20-R034.json",
    ),
    (
        "A17",
        "At most one automatic payout per rider per actual IST day",
        "PASS",
        "R027 one ₹15 AUTO and ₹10 pending approval; transactional/concurrent guard tests passed",
        "scenario-02-R027.json; tests/test_payments_database.py",
    ),
    (
        "A18",
        "Duplicate wamid and repeated claims never create duplicate payouts",
        "PASS",
        "Official repeated delivery has one ₹25 intent/provider entry; duplicate approval returns 409; concurrency tests passed",
        "scenario-05-R003.json; ops-payment-results.json; tests/test_messaging.py",
    ),
    (
        "A19",
        "Prior provider payments and ambiguity block unsafe obligations",
        "PASS",
        "Lost-response/reset/overlap tests passed; live ambiguous provider response recovered via ledger",
        "tests/test_payments_database.py; payment-observations.json",
    ),
    (
        "A20",
        "Durable intent before network POST; stable idempotency key",
        "PASS",
        "Persisted intent/key captured; existing worker claim and preflight path used; durability tests passed",
        "app/repositories/payment_jobs.py; tests/test_payments_database.py; scenario JSON snapshots",
    ),
    (
        "A21",
        "Concurrent worker claiming and lease recovery",
        "PASS",
        "Two-worker, crash-after-send and crash-before-network tests passed with controlled provider",
        "tests/test_payments_database.py",
    ),
    (
        "A22",
        "400/409/429/5xx/timeout handling and retry scheduling",
        "PASS",
        "Existing deterministic injected-failure tests all passed; real sandbox observed 201 and 504 with ledger recovery",
        "tests/test_payswift.py; tests/test_payments_database.py; payment-observations.json",
    ),
    (
        "A23",
        "UNKNOWN/NEEDS_REVIEW and provider restart safety",
        "PASS",
        "Controlled reset/unknown tests passed. Restarting in-memory provider remains an acknowledged limitation",
        "tests/test_payments_database.py; payswift/README.md",
    ),
    (
        "A24",
        "R016 exact ₹599/₹174/₹425 pending approval before Ops",
        "PASS",
        "Baseline 599 expected,174 historical,425 difference; one pending case, zero intents",
        "scenario-10-R016.json",
    ),
    (
        "A25",
        "Authenticated R016 approval, one durable ₹425 intent and confirmed payout",
        "PASS",
        "17 live Ops checks passed; exactly one OPS_APPROVED intent, matching provider ₹425, repeated approval 409",
        "ops-R016.json",
    ),
    (
        "A26",
        "Independent R034 authenticated rejection, reason/audit, no payment",
        "PASS",
        "17 live Ops checks passed; rejected queue, no intent/ledger entry, repeat rejected",
        "ops-R034.json",
    ),
    (
        "A27",
        "Correct intent, date-only investigation, corrections and context",
        "PARTIAL",
        "23 live decision successes; contextual/correction tests pass; R005 bonus scope failure remains",
        "app/agent/nodes.py; tests/test_agent_context.py; live-24-results.json",
    ),
    (
        "A28",
        "Trusted rider/trip ownership; spoofing and injection resistance",
        "PASS",
        "Live R020 cannot become another rider; ownership/injection/tool fencing tests passed",
        "scenario-04-R020.json; tests/test_agent_tools.py; tests/test_agent_graph.py",
    ),
    (
        "A29",
        "Ask for missing details rather than fabricate; support record disagreement",
        "PASS",
        "Live vague R003 and disagreement R011 pass; invalid-scope regressions passed",
        "scenario-01-R003.json; scenario-03-R011.json; tests/test_agent_context.py",
    ),
    (
        "A30",
        "Multiple simultaneous complaints and follow-up status",
        "PASS",
        "Live R027 separates surge/penalty and routes second AUTO to approval; live status turns pass",
        "scenario-02-R027.json; tests/test_claim_status.py",
    ),
    (
        "A31",
        "English, Hindi and Hinglish with plain truthful status",
        "PARTIAL",
        "Language/template tests pass; live dataset facts correct except R005; deferred HTTP acknowledgments are generic English",
        "tests/test_rider_payment_language.py; tests/test_agent_education.py; live-24-results.json",
    ),
    (
        "A32",
        "LLM failures handled without silent mocked fallback",
        "PASS",
        "Two unavailable live extractions and nine foreground cancellations resumed durably; no mock model used",
        "llm-metrics.json; ai-logs/final-audit/*-llm.json",
    ),
    (
        "A33",
        "No private chain-of-thought, raw credentials or tool argument leakage in SSE",
        "PASS",
        "Payload schema/stream privacy tests passed; audit logs contain structured tool arguments, not model private reasoning",
        "tests/test_realtime.py; app/realtime/events.py",
    ),
    (
        "A34",
        "Authenticated Ops login/session/logout and unauthorized rejection",
        "PASS",
        "Real authenticated HTTP checks on R016/R034 passed; full auth/CSRF/rate-limit suite passed",
        "ops-payment-results.json; tests/test_ops_endpoints.py",
    ),
    (
        "A35",
        "Approval/rejection/escalation assignment and resolution APIs",
        "PASS",
        "Live approval/rejection plus controlled real API escalation assignment/resolution tests passed",
        "ops-payment-results.json; tests/test_ops_endpoints.py::test_escalation_assignment_resolution_and_wrong_type",
    ),
    (
        "A36",
        "Human takeover, rider replies, internal-note privacy, AI suppression",
        "PASS",
        "Live R016/R034 takeover/reply/note/suppression/privacy checks passed",
        "ops-payment-results.json",
    ),
    (
        "A37",
        "In-flight AI fenced; sensitive handback blocked; safe handback supported",
        "PASS",
        "Live pending handback rejected; ownership race and safe handback API tests passed",
        "tests/test_ops_endpoints.py; ops-payment-results.json",
    ),
    (
        "A38",
        "Conversation resolution and attributed audit events",
        "PASS",
        "Both live Ops flows resolved; operator action tests/audit tests passed",
        "ops-payment-results.json; tests/test_ops_endpoints.py",
    ),
    (
        "A39",
        "Simple Ops UI provides review, approve/reject and correct action boundaries",
        "PARTIAL",
        "UI builds and APIs pass; approval Assign-to-me action is shown but backend accepts assignment only for escalation",
        "frontend/src/components/ops/approvals.tsx; app/services/ops_case_service.py",
    ),
    (
        "A40",
        "Real Redis event publication after commits and rollback safety",
        "PASS",
        "Real Redis fanout and HTTP/service/worker flow tests passed; publishers are mocked only in unrelated tests",
        "tests/test_realtime.py::test_complete_rider_ops_worker_flow_with_real_redis",
    ),
    (
        "A41",
        "Authorized SSE, heartbeats, cleanup and session expiry",
        "PASS",
        "Real ASGI auth checks, generator heartbeat/disconnect/cancellation tests passed",
        "tests/test_realtime.py",
    ),
    (
        "A42",
        "Frontend query/mutation via TanStack, reconnect/refetch and no duplicate bubbles",
        "PASS",
        "26 frontend tests including stream identity/dedup/reconnect + HTTP hooks passed; source uses TanStack Query",
        "frontend/src/test/realtime.test.tsx; frontend/src/test/http-hooks.test.tsx; checks/frontend-test.txt",
    ),
    (
        "A43",
        "Full live-model→real-provider→Redis→SSE→browser rendering in one run",
        "NOT TESTED",
        "No browser opened. Components verified separately; live audit uses ASGI HTTP without browser EventSource",
        "infrastructure-results.md",
    ),
    (
        "A44",
        "GET /health returns 200 with ready PostgreSQL",
        "PASS",
        "Local API health and all isolated scenario health calls returned 200",
        "app/api/health.py; live-24-results.json",
    ),
    (
        "A45",
        "POST /messages request/reply shape and idempotent multi-turn contract",
        "PASS",
        "30 original request records returned 200 with reply; stored/replayed final response idempotent",
        "live-24-results.json; tests/test_messaging.py",
    ),
    (
        "A46",
        "Webhook receives 2xx within approximately 10 seconds",
        "PASS",
        f"30/30 <10s; maximum {metrics['max_webhook_seconds']}s. This is ACK timing, not final-answer timing.",
        "live-24-results.json",
    ),
    (
        "A47",
        "Original vendor webhook delivers the final useful rider answer",
        "FAIL",
        f"9/30 original responses were acknowledgments; completion required persisted-state polling and replay; only {metrics['delivery_pass']}/24 scenarios delivered all final replies in original responses",
        "live-24-results.json; app/services/message_service.py",
    ),
    (
        "A48",
        "GET /trace chronological required event schema",
        "PASS",
        "24/24 isolated responses contain at,type,name,input,output sorted by time",
        "live-24-results.json; ai-logs/final-audit/*-traces.json",
    ),
    (
        "A49",
        "GET /ops/pending IDs/types/amounts/reasons/timestamps; closed cases excluded",
        "PASS",
        "All isolated calls returned 200; pending entries and closed-entry exclusion tests passed",
        "live-24-results.json; tests/test_ops_endpoints.py",
    ),
    (
        "A50",
        "docker compose up starts the complete required system on 8000",
        "FAIL",
        "Compose declares postgres,redis,payswift,worker, but no API (or frontend); no automatic migration/seed orchestration",
        "docker-compose.yml; checks/compose-services.txt",
    ),
    (
        "A51",
        "Migrations apply/check/downgrade in disposable PostgreSQL",
        "PASS",
        "487-test suite ran fresh database migration cycle; audit template also migrated and seeded",
        "tests/conftest.py; checks/backend-pytest.txt; checks/audit-migrations.txt",
    ),
    (
        "A52",
        "PAYSWIFT_BASE_URL and backend/provider connectivity",
        "PASS",
        "PaySwift client reads environment; audit uses a fresh per-scenario URL; original sandbox untouched",
        "app/core/config.py; app/integrations/payswift.py; checks/sandbox-start-probe.txt",
    ),
    (
        "A53",
        "Required service health, worker availability and Redis connectivity",
        "PASS",
        "Local API/provider health OK; local worker running; configured Redis PING true; isolated worker functions exercised",
        "checks/local-runtime-processes.json; checks/compose-ps.jsonl; infrastructure-results.md",
    ),
    (
        "A54",
        "Supplied PaySwift service implementation preserved",
        "PASS",
        "No tracked payswift changes and bytecode SHA256 unchanged during audit",
        "audit-preservation.json; checks/security-scan.json",
    ),
    (
        "A55",
        "Portable one-command eval accepts service URL and only public interfaces",
        "FAIL",
        "python evals/run.py http://localhost:8000 exits 2 (missing file); internal audit harness is NOT a replacement",
        "checks/portable-evaluator.txt; evals/audit_live.py",
    ),
    (
        "A56",
        "One-page root README explains run/design/assumptions/evals/skips",
        "FAIL",
        "Root README is three-line assignment stub; detailed backend docs do not satisfy root submission README",
        "README.md; backend/README.md",
    ),
    (
        "A57",
        "Environment variables documented without secrets",
        "PARTIAL",
        "backend/.env.example and frontend/.env.example cover app settings; root example/setup instructions absent",
        "backend/.env.example; frontend/.env.example; README.md",
    ),
    (
        "A58",
        "Raw AI-assisted development session exports in ai-logs",
        "FAIL",
        "Before audit only ai-logs/README.md existed. New sanitized model-evaluation logs are not development-session exports",
        "ai-logs/README.md; ai-logs/final-audit/README.md",
    ),
    (
        "A59",
        "GitHub Actions triggers push/main, PR/main, manual; least privilege",
        "PASS",
        "YAML parsed; triggers and permissions contents:read correct; backend,frontend,DB jobs defined",
        "checks/workflow-syntax.json; .github/workflows/workflow.yml",
    ),
    (
        "A60",
        "CI checks run locally and active action refs exist",
        "PASS",
        "Backend 487 passed/1 skipped, Ruff clean, frontend 26 tests/lint/types/build clean; four active SHA commit pages verified",
        "checks/; checks/action-references.json",
    ),
    (
        "A61",
        "Actual remote GitHub Actions run succeeds on submitted main",
        "NOT TESTED",
        "No workflow dispatched or push performed; working tree is dirty and uncommitted",
        "manifest.json; .github/workflows/workflow.yml",
    ),
    (
        "A62",
        "No committed credentials",
        "PARTIAL",
        "No tracked .env or recognizable AWS/Groq/private-key patterns in tracked working tree; complete history secret scan not done",
        "checks/security-scan.json",
    ),
    (
        "A63",
        "Private non-fork repository and Sarthak-pyard collaborator",
        "NOT TESTED",
        "Remote repository settings/collaborator access require manual confirmation; no invitations sent",
        "SUBMISSION.md",
    ),
    (
        "A64",
        "Submit main before 24-hour deadline with repository link",
        "NOT TESTED",
        "Email receipt/deadline not available; no commit, push, deployment or email performed",
        "BRIEF.md; SUBMISSION.md",
    ),
]
counts = dict(collections.Counter(row[2] for row in criteria))
(OUT / "compliance-results.json").write_text(
    json.dumps(
        {
            "counts": counts,
            "criteria": [
                dict(
                    zip(
                        ["id", "requirement", "status", "evidence", "implementation_or_artifacts"],
                        r,
                    )
                )
                for r in criteria
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
    + "\n"
)
write(
    "compliance-matrix.md",
    f"# Assignment compliance matrix\n\n{len(criteria)} individually evaluated criteria. Status counts: "
    + ", ".join(f"{k}: {v}" for k, v in counts.items())
    + ".\n\nPASS describes the stated proof scope, not a claim that all LLM conversations or all provider failure modes are perfect. Paths beginning app/ or tests/ are relative to backend/.\n\n| ID | Requirement | Status | Actual evidence | Implementation / reproduction |\n|---|---|---|---|---|\n"
    + "\n".join("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in criteria),
)

# Keep payment authorization and actual external confirmation independently visible.
ops_result = {
    "provider": "unchanged supplied PaySwift server.pyc, isolated process per live scenario",
    "live_approval": ops["R016"],
    "live_rejection": ops["R034"],
    "deterministic_reliability_suite": {
        "status": "PASS",
        "evidence": "checks/backend-pytest.txt",
        "tests": "backend/tests/test_payments_database.py; backend/tests/test_payswift.py; backend/tests/test_ops_endpoints.py",
        "provider": "controlled fake for failure injection",
        "real_sandbox_opt_in_test": "SKIPPED by existing suite; independently superseded for settlement evidence by this live audit, NOT reported as a passed pytest",
    },
    "amount_summary": {
        "auto_confirmed": metrics["confirmed_auto_amount"],
        "ops_approved_confirmed": 425,
        "total_isolated_sandbox_confirmed": metrics["confirmed_auto_amount"] + 425,
        "missing_expected_incentive": 150,
    },
    "known_limitations": [
        "PaySwift ledger/idempotency memory resets on provider restart.",
        "No exactly-once settlement guarantee claimed.",
        "Worker restart/lease faults tested with controlled provider, not by killing a real in-flight money process.",
        "Production/development PaySwift ledger was not reset or used for audit transfers.",
    ],
}
(OUT / "ops-payment-results.json").write_text(
    json.dumps(ops_result, indent=2, ensure_ascii=False) + "\n"
)

observations = []
for path in (ROOT / "ai-logs/final-audit").glob("*-traces.json"):
    for event in json.loads(path.read_text()):
        if event["name"] == "payswift_request_result":
            observations.append({"scenario": path.name.split("-traces")[0], **event})
(OUT / "payment-observations.json").write_text(
    json.dumps(observations, indent=2, ensure_ascii=False) + "\n"
)

scenario_lines = [
    "# All 24 live official scenarios",
    "",
    "Provider: Amazon Bedrock `us.amazon.nova-pro-v1:0`; prompt `quickdrop-extraction-v6`. Real extraction on 23 scenarios, real LangGraph and tools on all 24, real unchanged isolated PaySwift. R037 short-circuited in the input-policy guard before the LLM. No labels or mocked model responses.",
    "",
    "**Decision** compares persisted AUTO intent amounts and pending approval amounts with original expectations. **Execution** requires the expected amount to be confirmed by a correlated PaySwift ledger entry; no-payout cases must have no unexpected transfer. **Delivery** requires the original webhook reply to contain the final answer. An acknowledgment followed by a later database reply is a delivery failure, even if eventual money handling is correct.",
    "",
    f"Eventual decisions/outcomes: {metrics['eventual_pass']}/24. Strict original-webhook end-to-end: {metrics['end_to_end_pass']}/24. Authorized AUTO payouts: 10/10 externally confirmed; R005 produced no intent and therefore is not a passing worker test.",
    "",
    "| # | Rider | Expected AUTO / approval ₹ | Authorized AUTO / approval ₹ | PaySwift-confirmed ₹ | Decision | Execution | Delivery | End-to-end |",
    "|---|---|---|---|---|---|---|---|---|",
]
for r in rows:
    e = r["expected"]
    choices = e.get("one_of", [{"payout": e.get("payout", 0), "approval": e.get("approval")}])
    expected = " or ".join(
        f"{o['payout']} / {o['approval'] if o['approval'] is not None else '—'}" for o in choices
    )
    scenario_lines.append(
        f"| {r['scenario_id']} | {r['rider_id']} | {expected} | {r['auto_authorized_amount']} / {r['pending_approval_amount'] if r['pending_approval_amount'] is not None else '—'} | {r['provider_confirmed_amount']} | {r['decision_status']} | {r['execution_status']} | {r['delivery_status']} | {r['end_to_end_status']} |"
    )
for r in rows:
    n = r["scenario_id"]
    stem = f"scenario-{n:02d}-{r['rider_id']}"
    scenario_lines += [
        "",
        f"## {n}. {r['rider_id']}: {r['scenario']}",
        "",
        f"- Rider turns: {len(r['turns'])}. LLM invocations: {r['llm_calls']}. Expected escalation: {r['expected'].get('escalation')}; actual agent escalations: {r['agent_escalation_count']}, all queue escalations: {r['all_escalation_count']}.",
        f"- Original webhook latency: "
        + ", ".join(f"{t['webhook_latency_seconds']:.3f}s" for t in r["turns"])
        + ". Final agent completion: "
        + ", ".join(f"{t['total_agent_seconds']:.3f}s" for t in r["turns"])
        + ".",
        "- Persisted verified dispute amounts: "
        + str(r["verified_dispute_amounts"])
        + ". Provider-confirmed: ₹"
        + str(r["provider_confirmed_amount"])
        + ". Conditional worker result: "
        + r["worker_execution_status"]
        + ".",
        "- Tools observed: " + ", ".join(dict.fromkeys(r["tool_calls"])) + ".",
        f"- Evidence: [{stem}.json]({stem}.json), [LLM interactions](../../../ai-logs/final-audit/{stem}-llm.json), [chronological traces](../../../ai-logs/final-audit/{stem}-traces.json).",
        "- Result: "
        + r["end_to_end_status"]
        + " strict end-to-end; "
        + r["eventual_scenario_status"]
        + " eventual financial/semantic outcome.",
    ]
    if not r["llm_calls"]:
        scenario_lines += [
            "- No LLM invocation: the application input-policy guard rejected the injection before model execution. Empty LLM log records zero calls; this passes safety routing but does not satisfy literal 24/24 live-model invocation coverage."
        ]
    if n == 6:
        scenario_lines += [
            "- Failure: model extracted PAYOUT for yesterday and omitted INCENTIVE. Fare reconciliation found no trip shortfall and replied that nothing was owed, missing the required ₹150 daily bonus. This is an understanding/scope failure, not a PaySwift rejection or an eligibility-clock failure. Initial foreground call was cancelled; the real model retry produced the incorrect scope. No expectations, prompts or source records were changed during this audit."
        ]
    if r["delivery_status"] == "FAIL":
        scenario_lines += [
            "- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path."
        ]
    if n == 15:
        scenario_lines += [
            "- R007 decision and payment execution both passed here: one ₹34 AUTO intent, saved SUCCEEDED state and matching provider payout/reference. This isolated result does not repair or certify any older development NEEDS_REVIEW intent. The original webhook still deferred."
        ]
write("scenario-results.md", "\n".join(scenario_lines))

write(
    "infrastructure-results.md",
    f"""# Infrastructure and integration results

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

A current tracked-tree pattern scan found no tracked `.env`, recognizable AWS access key, Groq key or private-key block. This is **not** a complete Git-history secret audit. No credentials/cookies/session tokens were exported into audit artifacts. Source/bytecode hashes are preserved in [audit-preservation.json](audit-preservation.json). Git commit tested: `{manifest["git_commit"]}` plus the dirty working tree recorded in [manifest.json](manifest.json); results do not certify an unpushed `main` revision.
""",
)

defects = [
    (
        "D01",
        "P0",
        "Compose does not start the required API",
        "Run docker compose config --services; there is no API service or port 8000. backend/Dockerfile defaults to worker. A clean full application cannot satisfy the required one-command startup.",
        "docker-compose.yml; backend/Dockerfile",
        "Add explicit API startup and database initialization ordering, then test clean Compose startup in a disposable project. Preserve supplied payswift service.",
    ),
    (
        "D02",
        "P0",
        "Portable assignment evaluator missing",
        "python evals/run.py http://localhost:8000 exits 2. Internal audit harness imports backend and cannot be run against other implementations.",
        "evals/run.py (absent); checks/portable-evaluator.txt",
        "Implement the separately required URL-taking black-box evaluator using only /messages, /trace, /ops/pending and PaySwift; document one command.",
    ),
    (
        "D03",
        "P0",
        "Required raw AI development-session exports absent",
        "Before audit ai-logs contained only README.md. Audit LLM extracts are evidence, not raw exports of development assistant sessions.",
        "ai-logs/README.md; SUBMISSION.md",
        "Export the actual development sessions, review/redact secrets as required, and document export provenance. Do not substitute summaries or audit traces.",
    ),
    (
        "D04",
        "P1",
        "Live R005 misses the ₹150 incentive",
        "Replay original kal ka payout kam aaya hai. 12 se zyada order kiye the maine. Real Nova extracts PAYOUT only. Trip-fare reconciliation returns no shortfall; no intent or provider payout. Expected ₹150.",
        "backend/app/agent/prompts.py: complaint kinds; backend/app/agent/nodes.py; scenario-06-R005.json",
        "Investigate applicable daily bonus evidence when an earnings complaint plus trip-count context suggests incentive eligibility; do not guess money from claimed counts. Retain original scenario expectations and add a live regression.",
    ),
    (
        "D05",
        "P1",
        "Final vendor reply unavailable after successful acknowledgment",
        "Nine of 30 original HTTP 200 responses were processing acknowledgments. Final answers appear only after durable worker completion and explicit replay/state reads. Vendor stops retrying on 2xx; no outbound final-send integration exists.",
        "backend/app/services/message_service.py: execute/defer/process; live-24-results.json",
        "Fit useful final decisions within the vendor response budget, or integrate a real outbound final-reply transport and document it. Do not report acknowledgment latency as final-answer latency.",
    ),
    (
        "D06",
        "P1",
        "Root submission README incomplete",
        "README.md is the original three-line stub with no setup, agent design, assumptions, eval results or skipped work.",
        "README.md; BRIEF.md; SUBMISSION.md",
        "Write the required one-page root submission README from measured results, including known failures and exact startup/eval commands.",
    ),
    (
        "D07",
        "P2",
        "Assign-to-me shown on financial approvals but backend rejects it",
        "Inspect the shared Assign to me button in CaseReview and ops_case_service.act: assign requires type escalation. Approve directly works; this assignment affordance does not. No browser action was executed in audit.",
        "frontend/src/components/ops/approvals.tsx: CaseReview; backend/app/services/ops_case_service.py: act",
        "Hide unsupported assignment on approvals or implement compatible assignment rules with endpoint tests.",
    ),
    (
        "D08",
        "P2",
        "Ops evidence-check panel has no actual check rows",
        "opsApi.load maps every case to checks: []; CaseReview uses checks.slice(0,6).every, which returns true for an empty list. Server revalidates approval, so this is not proof of unsafe payment authorization.",
        "frontend/src/lib/api/ops.ts: checks; frontend/src/components/ops/approvals.tsx: eligible",
        "Populate checks from actual persisted evidence or show unavailable explicitly; do not imply all checks passed from an empty array.",
    ),
    (
        "D09",
        "P2",
        "Root environment/startup documentation incomplete",
        "Backend/frontend examples exist but root .env.example and root run instructions are absent; Compose requires POSTGRES_PASSWORD.",
        "backend/.env.example; frontend/.env.example; README.md; docker-compose.yml",
        "Provide a root environment/setup entry point that lists Compose-required values without credentials.",
    ),
]
priority_counts = dict(collections.Counter(d[1] for d in defects))
write(
    "defects.md",
    "# Submission defects\n\nNo product fixes were applied during this audit. Every observed failure is retained; original expectations and source data were not changed.\n\n"
    + "\n\n".join(
        f"## {id} — {priority}: {title}\n\nReproduction/evidence: {repro}\n\nLocation: `{location}`.\n\nRecommended fix: {fix}"
        for id, priority, title, repro, location, fix in defects
    ),
)

summary = f"""# QuickDrop final submission audit

## 1. Executive summary

**Verdict: NOT SUBMISSION-READY.** No unsafe overpayment was observed in the tested paths, but mandatory deployment/evaluation/submission artifacts are missing, the live R005 scenario fails, and the original webhook does not always deliver the final answer.

- Audited on 29 October 2026, Asia/Kolkata. Commit: `{manifest["git_commit"]}` **plus uncommitted working-tree changes**. See [manifest](manifest.json) and [source preservation](audit-preservation.json).
- Actual model: Amazon Bedrock **`{data["model"]}`**, prompt `{data["prompt_version"]}`. All 24 used the actual configured graph. **23 invoked the real LLM; R037 was rejected by the input-policy guard before any model call.** No model invocation was fabricated to claim literal 24/24 LLM coverage. Credentials were used securely; no labels or mocked LLM fallback.
- **Agent financial decisions: {metrics["decision_pass"]}/24 PASS. Expected payout/execution outcomes: {metrics["execution_pass"]}/24 PASS. Eventual scenario outcomes: {metrics["eventual_pass"]}/24 PASS.** Zero-transfer cases are included in those counts.
- **Original-webhook end-to-end: {metrics["end_to_end_pass"]}/24 PASS.** Nine scenarios had a deferred initial reply. These are not relabeled as original-transport passes because later processing succeeded.
- **Actual authorized AUTO payouts: 10/10 provider-confirmed, ₹514 total.** Missing expected R005 ₹150 produced no intent; it is not a passing worker execution. Human-approved R016 ₹425 also confirmed. No unresolved created intent remained in this isolated run.
- **R007:** correct ₹34 decision **and** one correlated successful ₹34 provider payout; original webhook still deferred. This does not certify or recover earlier development R007 records.
- Existing backend tests: **487 passed, 1 skipped**. Frontend: **26 passed**, lint/typecheck/build passed. Ruff lint/format passed.
- Compliance: **{counts.get("PASS", 0)}/{len(criteria)} PASS**, {counts.get("FAIL", 0)} FAIL, {counts.get("PARTIAL", 0)} PARTIAL, {counts.get("NOT TESTED", 0)} NOT TESTED. These are separate criteria, not a readiness percentage.
- Defects: **{priority_counts.get("P0", 0)} P0, {priority_counts.get("P1", 0)} P1, {priority_counts.get("P2", 0)} P2**. P0 entries are mandatory assignment/submission failures; no P0 overpayment was found.

## 2. Assignment compliance matrix

The full requirement/implementation/test/expected-versus-actual matrix is [compliance-matrix.md](compliance-matrix.md), with machine-readable rows in [compliance-results.json](compliance-results.json). Four criteria require manual/unperformed proof, including remote repository collaborator access and deadline/submission status. Literal real-model invocation coverage is partial because R037 was rejected before the model.

## 3. All 24 live scenarios

See [scenario-results.md](scenario-results.md) and [live-24-results.json](live-24-results.json). Each scenario also has an individual JSON snapshot, original request bodies, webhook/final replies, timing, disputes/items, intents, queue records, pending endpoint output, tool/decision events and real provider ledger.

**Decision and execution are independent.** A stored correct shortfall or an approval is not proof of money being sent. A SUCCEEDED flag without a matching amount/rider/reference/provider ledger entry is not counted as a confirmed payout. Original expectations, including one_of and optional escalation, are honored unchanged.

R005 failed because the live model classified the count-qualified earnings complaint as PAYOUT only and never investigated the daily bonus. It returned no unpaid balance and sent ₹0 instead of the expected ₹150. This is a scope-understanding defect; timestamps were preserved and the provider did not reject an attempted ₹150 payout. Original fixtures with predefined incentive extraction still pass, demonstrating why the live run was necessary.

All 30 original request records returned HTTP 200 within 10 seconds; maximum **{metrics["max_webhook_seconds"]:.4f}s**. However, **{metrics["acknowledgment_turns"]}/30** were acknowledgments rather than final replies. Durable continuation completed later, up to **{metrics["max_final_agent_seconds"]:.4f}s** from submission. The harness waited, then replayed the exact message ID to retrieve the cached final answer. This is explicitly extra observation, not evidence that the original vendor received that final answer.

Model evidence: {llm["invocations"]} observed invocations, {llm["validated_responses"]} validated responses, {llm["foreground_cancellations"]} foreground cancellations and {llm["extraction_unavailable"]} extraction-unavailable errors. These failures were not hidden or replaced with mocks. Wrapper-observed mean latency was {llm["mean_invocation_seconds"]}s. Cancelling a wrapper around a synchronous SDK thread does not prove cancellation of the upstream billed request. [Metrics](llm-metrics.json), [sanitized interactions](../../../ai-logs/final-audit/README.md).

## 4. Human Ops results

Both independently isolated live API flows passed all 17 recorded checks. [Machine-readable Ops/payment results](ops-payment-results.json).

- R016 baseline: ₹599 expected, ₹174 historical, ₹425 verified; exactly one pending approval and no pre-approval payment intent. Authenticated approval created one durable OPS_APPROVED intent. Existing worker confirmed ₹425 against the supplied isolated sandbox. A repeated approve request returned 409 with no duplicate transfer.
- R034 baseline: ₹249 approval case. Authenticated rejection recorded a reason, rejected the queue/dispute, created no intent, and left the provider ledger empty. Repeated rejection was refused.
- Both flows verified authentication/session/logout, takeover, public human reply, private-note exclusion from rider reads, AI suppression in HUMAN mode, blocked pending handback, and conversation resolution after blockers cleared.
- Escalation assignment/resolution, safe handback and in-flight ownership fencing passed the existing actual API integration tests with a controlled provider. They are not claimed as additional live-LLM scenario runs.
- UI caveat: approval cases expose an assignment action that the backend only permits for escalation cases. Direct approval worked in the live API test.

## 5. Payment reliability

- Scenario AUTO transfers: 10 matching provider payouts totaling ₹514; authenticated human approval adds one ₹425 payout. Each scenario had a fresh ledger. These are sandbox transfers, not real bank money.
- The baseline real-worker trace set observed nine `201` confirmations and one uncertain `504`, followed by successful GET-ledger reconciliation; no second POST was required for that logical payout. See [payment-observations.json](payment-observations.json).
- Controlled-provider tests verified 400/409/429/5xx/timeout handling, Retry-After scheduling, durable claims, concurrent workers, stable keys, lost responses, lease/crash recovery, source-credit changes, UNKNOWN/NEEDS_REVIEW, overlapping scopes and provider-reset safety.
- The suite's explicit opt-in sandbox pytest was skipped. The separate live harness provides real sandbox evidence; the skipped test is not mislabeled as passed.
- Provider ledger and idempotency memory are lost on restart. No exactly-once settlement guarantee is made. No existing development intent was reset, retried or paid by the audit.

## 6. Frontend and realtime

Frontend lint, 26 tests, TypeScript generation/check and production build passed. Real Redis fanout and HTTP/service/worker integration passed controlled tests; authentication, SSE chunks/heartbeats/cleanup, public-vs-private events and payment-confirmation events passed. Frontend mocks verified message dedup, reconnect/refetch and normal TanStack Query reads/mutations. **The entire live-LLM/real-provider pipeline was not exercised in a browser.** No browser was opened. See [infrastructure-results.md](infrastructure-results.md) for this proof boundary.

The activity UI shows public operation progress, not private reasoning. Reply deltas are chunks of a committed safe final reply, not raw model-token generation. The Ops UI currently maps check rows to an empty list, so its evidence affordance is incomplete even though server-side approval safety remains enforced.

## 7. Defects and recommended fixes

See [defects.md](defects.md). Priority order: complete Compose API startup; add the portable public-interface evaluator; supply raw development AI exports; fix R005 daily-bonus discovery; fix original-vendor final-answer delivery; replace the root README stub; correct approval assignment and evidence-check UI affordances. No prompts, business policy, model answers, CSVs or expected outcomes were altered to force passes.

## 8. Final submission checklist

Completed: live 24-scenario evaluation, isolated real settlement checks, authenticated approval/rejection flows, full backend suite, frontend lint/tests/types/build, Ruff, migration validation, Compose syntax/health inspection, workflow YAML parsing and active action-SHA existence checks, source hash preservation, sanitized evidence and separate decision/execution/delivery reporting.

Pending/blocking: all defects D01–D06; actual portable evaluator; complete clean Compose startup; required raw AI development-session exports; concise root setup/design/results README. Manual verification remains for private non-fork repository, Sarthak-pyard collaborator, actual remote CI run, committed/pushed main, and email deadline/link submission. A complete Git-history secret audit and one real browser end-to-end run remain unperformed.

Reproduce internal live audit: `uv run --directory backend python ../evals/audit_live.py`. Requires local development PostgreSQL with CREATEDB, configured live LLM credentials and Docker/redis:7-alpine. It creates/drops only generated quickdrop_audit_* databases, starts its own Redis and supplied sandbox processes, and does not use the developer's ledger. Preserve the current report directory before rerunning: stochastic model/provider results can differ. This is **not** the missing required portable `python evals/run.py URL` evaluator.
"""
write("AUDIT_REPORT.md", summary)
write(
    "REPRODUCING.md",
    """# Reproducing this audit

From repository root:

```sh
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run --directory backend python ../evals/audit_live.py
python evals/build_audit_report.py
```

Keep the current evidence folder before repeating the live audit. The audit harness
requires local PostgreSQL CREATEDB, the existing locked backend environment, the
configured real LLM credentials, Docker and a local redis:7-alpine image. It creates
fresh cloned DBs and fresh supplied sandbox processes, preserves scenario identities
and original timestamps, and uses actual FastAPI ASGI HTTP routes. It does not use
browser automation or alter the application's prompts/policy/data. Real model calls
may incur API charges; the provided sandbox transfers are simulated only.

The portable `evals/run.py URL` command is missing and deliberately reported FAIL.
The internal harness depends on backend internals and therefore cannot replace it.
The report's delivery result requires the original webhook reply to be final; eventual
worker completion plus polling/replay is reported separately. Inspect JSON evidence
rather than treating a process exit code as a count of passed official scenarios.
""",
)
(
    ROOT / "ai-logs/final-audit/README.md"
).write_text("""# Sanitized live-evaluation model interaction evidence

These files record actual configured Nova Pro calls during all 24 original scenarios.
Each *-llm.json contains application-supplied text, effective timestamp, bounded
history/context, prompt version/hash, provider/model, wrapper elapsed time and the
validated structured model output or failure class. No canned model answers were
used. Cancelled calls are retained; upstream synchronous SDK work may outlive wrapper
cancellation. Hidden model reasoning, credentials, cookies and session tokens are not
recorded. *-traces.json contains the chronological public assignment trace API output.

These are evaluation interactions, NOT exports of the assistant development sessions
required by SUBMISSION.md. Those raw development-session exports remain missing and
are explicitly recorded as a submission defect. Do not claim these sanitized audit
artifacts satisfy that separate requirement.
""")
print(json.dumps({"compliance": counts, "defects": priority_counts, "live": metrics}, indent=2))
