# QuickDrop final submission audit

## 1. Executive summary

**Verdict: NOT SUBMISSION-READY.** No unsafe overpayment was observed in the tested paths, but mandatory deployment/evaluation/submission artifacts are missing, the live R005 scenario fails, and the original webhook does not always deliver the final answer.

- Audited on 29 October 2026, Asia/Kolkata. Commit: `7ac75f820a4f67e15e2e0eedffad1bcd9391da16` **plus uncommitted working-tree changes**. See [manifest](manifest.json) and [source preservation](audit-preservation.json).
- Actual model: Amazon Bedrock **`us.amazon.nova-pro-v1:0`**, prompt `quickdrop-extraction-v6`. All 24 used the actual configured graph. **23 invoked the real LLM; R037 was rejected by the input-policy guard before any model call.** No model invocation was fabricated to claim literal 24/24 LLM coverage. Credentials were used securely; no labels or mocked LLM fallback.
- **Agent financial decisions: 23/24 PASS. Expected payout/execution outcomes: 23/24 PASS. Eventual scenario outcomes: 23/24 PASS.** Zero-transfer cases are included in those counts.
- **Original-webhook end-to-end: 15/24 PASS.** Nine scenarios had a deferred initial reply. These are not relabeled as original-transport passes because later processing succeeded.
- **Actual authorized AUTO payouts: 10/10 provider-confirmed, ₹514 total.** Missing expected R005 ₹150 produced no intent; it is not a passing worker execution. Human-approved R016 ₹425 also confirmed. No unresolved created intent remained in this isolated run.
- **R007:** correct ₹34 decision **and** one correlated successful ₹34 provider payout; original webhook still deferred. This does not certify or recover earlier development R007 records.
- Existing backend tests: **487 passed, 1 skipped**. Frontend: **26 passed**, lint/typecheck/build passed. Ruff lint/format passed.
- Compliance: **46/64 PASS**, 7 FAIL, 7 PARTIAL, 4 NOT TESTED. These are separate criteria, not a readiness percentage.
- Defects: **3 P0, 3 P1, 3 P2**. P0 entries are mandatory assignment/submission failures; no P0 overpayment was found.

## 2. Assignment compliance matrix

The full requirement/implementation/test/expected-versus-actual matrix is [compliance-matrix.md](compliance-matrix.md), with machine-readable rows in [compliance-results.json](compliance-results.json). Four criteria require manual/unperformed proof, including remote repository collaborator access and deadline/submission status. Literal real-model invocation coverage is partial because R037 was rejected before the model.

## 3. All 24 live scenarios

See [scenario-results.md](scenario-results.md) and [live-24-results.json](live-24-results.json). Each scenario also has an individual JSON snapshot, original request bodies, webhook/final replies, timing, disputes/items, intents, queue records, pending endpoint output, tool/decision events and real provider ledger.

**Decision and execution are independent.** A stored correct shortfall or an approval is not proof of money being sent. A SUCCEEDED flag without a matching amount/rider/reference/provider ledger entry is not counted as a confirmed payout. Original expectations, including one_of and optional escalation, are honored unchanged.

R005 failed because the live model classified the count-qualified earnings complaint as PAYOUT only and never investigated the daily bonus. It returned no unpaid balance and sent ₹0 instead of the expected ₹150. This is a scope-understanding defect; timestamps were preserved and the provider did not reject an attempted ₹150 payout. Original fixtures with predefined incentive extraction still pass, demonstrating why the live run was necessary.

All 30 original request records returned HTTP 200 within 10 seconds; maximum **5.5661s**. However, **9/30** were acknowledgments rather than final replies. Durable continuation completed later, up to **23.9791s** from submission. The harness waited, then replayed the exact message ID to retrieve the cached final answer. This is explicitly extra observation, not evidence that the original vendor received that final answer.

Model evidence: 38 observed invocations, 27 validated responses, 9 foreground cancellations and 2 extraction-unavailable errors. These failures were not hidden or replaced with mocks. Wrapper-observed mean latency was 3.533s. Cancelling a wrapper around a synchronous SDK thread does not prove cancellation of the upstream billed request. [Metrics](llm-metrics.json), [sanitized interactions](../../../ai-logs/final-audit/README.md).

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
