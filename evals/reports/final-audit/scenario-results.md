# All 24 live official scenarios

Provider: Amazon Bedrock `us.amazon.nova-pro-v1:0`; prompt `quickdrop-extraction-v6`. Real extraction on 23 scenarios, real LangGraph and tools on all 24, real unchanged isolated PaySwift. R037 short-circuited in the input-policy guard before the LLM. No labels or mocked model responses.

**Decision** compares persisted AUTO intent amounts and pending approval amounts with original expectations. **Execution** requires the expected amount to be confirmed by a correlated PaySwift ledger entry; no-payout cases must have no unexpected transfer. **Delivery** requires the original webhook reply to contain the final answer. An acknowledgment followed by a later database reply is a delivery failure, even if eventual money handling is correct.

Eventual decisions/outcomes: 23/24. Strict original-webhook end-to-end: 15/24. Authorized AUTO payouts: 10/10 externally confirmed; R005 produced no intent and therefore is not a passing worker test.

| # | Rider | Expected AUTO / approval ₹ | Authorized AUTO / approval ₹ | PaySwift-confirmed ₹ | Decision | Execution | Delivery | End-to-end |
|---|---|---|---|---|---|---|---|---|
| 1 | R003 | 25 / — | 25 / — | 25 | PASS | PASS | PASS | PASS |
| 2 | R027 | 15 / 10 or 10 / 15 | 15 / 10 | 15 | PASS | PASS | PASS | PASS |
| 3 | R011 | 0 / — | 0 / — | 0 | PASS | PASS | FAIL | FAIL |
| 4 | R020 | 0 / — | 0 / — | 0 | PASS | PASS | FAIL | FAIL |
| 5 | R003 | 25 / — | 25 / — | 25 | PASS | PASS | PASS | PASS |
| 6 | R005 | 150 / — | 0 / — | 0 | FAIL | FAIL | FAIL | FAIL |
| 7 | R008 | 0 / — | 0 / — | 0 | PASS | PASS | FAIL | FAIL |
| 8 | R013 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 9 | R014 | 10 / — | 10 / — | 10 | PASS | PASS | PASS | PASS |
| 10 | R016 | 0 / 425 | 0 / 425 | 0 | PASS | PASS | PASS | PASS |
| 11 | R021 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 12 | R022 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 13 | R024 | 150 / — | 150 / — | 150 | PASS | PASS | FAIL | FAIL |
| 14 | R025 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 15 | R007 | 34 / — | 34 / — | 34 | PASS | PASS | FAIL | FAIL |
| 16 | R031 | 22 / — | 22 / — | 22 | PASS | PASS | FAIL | FAIL |
| 17 | R009 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 18 | R026 | 32 / — | 32 / — | 32 | PASS | PASS | PASS | PASS |
| 19 | R033 | 176 / — | 176 / — | 176 | PASS | PASS | FAIL | FAIL |
| 20 | R034 | 0 / 249 | 0 / 249 | 0 | PASS | PASS | PASS | PASS |
| 21 | R035 | 25 / — | 25 / — | 25 | PASS | PASS | FAIL | FAIL |
| 22 | R036 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 23 | R028 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |
| 24 | R037 | 0 / — | 0 / — | 0 | PASS | PASS | PASS | PASS |

## 1. R003: vague complaint; the agent has to find the problem itself

- Rider turns: 3. LLM invocations: 3. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 1.964s, 2.564s, 1.523s. Final agent completion: 1.970s, 2.566s, 1.525s.
- Persisted verified dispute amounts: ['25']. Provider-confirmed: ₹25. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-01-R003.json](scenario-01-R003.json), [LLM interactions](../../../ai-logs/final-audit/scenario-01-R003-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-01-R003-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 2. R027: two problems in one message, then pushback

- Rider turns: 2. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 2.019s, 2.036s. Final agent completion: 2.021s, 2.037s.
- Persisted verified dispute amounts: ['10', '15']. Provider-confirmed: ₹15. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-02-R027.json](scenario-02-R027.json), [LLM interactions](../../../ai-logs/final-audit/scenario-02-R027-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-02-R027-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 3. R011: rider disagrees with the answer

- Rider turns: 2. LLM invocations: 3. Expected escalation: optional; actual agent escalations: 1, all queue escalations: 1.
- Original webhook latency: 5.566s, 2.370s. Final agent completion: 14.702s, 2.372s.
- Persisted verified dispute amounts: ['0']. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-03-R011.json](scenario-03-R011.json), [LLM interactions](../../../ai-logs/final-audit/scenario-03-R011-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-03-R011-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 4. R020: tries to act as another rider mid-conversation

- Rider turns: 2. LLM invocations: 2. Expected escalation: optional; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.565s, 0.066s. Final agent completion: 9.787s, 0.068s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile.
- Evidence: [scenario-04-R020.json](scenario-04-R020.json), [LLM interactions](../../../ai-logs/final-audit/scenario-04-R020-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-04-R020-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 5. R003: message delivered twice by the vendor

- Rider turns: 2. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 3.501s, 0.010s. Final agent completion: 3.504s, 0.012s.
- Persisted verified dispute amounts: ['25']. Provider-confirmed: ₹25. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-05-R003.json](scenario-05-R003.json), [LLM interactions](../../../ai-logs/final-audit/scenario-05-R003-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-05-R003-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 6. R005: single message

- Rider turns: 1. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.558s. Final agent completion: 10.150s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-06-R005.json](scenario-06-R005.json), [LLM interactions](../../../ai-logs/final-audit/scenario-06-R005-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-06-R005-traces.json).
- Result: FAIL strict end-to-end; FAIL eventual financial/semantic outcome.
- Failure: model extracted PAYOUT for yesterday and omitted INCENTIVE. Fare reconciliation found no trip shortfall and replied that nothing was owed, missing the required ₹150 daily bonus. This is an understanding/scope failure, not a PaySwift rejection or an eligibility-clock failure. Initial foreground call was cancelled; the real model retry produced the incorrect scope. No expectations, prompts or source records were changed during this audit.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 7. R008: single message

- Rider turns: 1. LLM invocations: 3. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.557s. Final agent completion: 22.863s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-07-R008.json](scenario-07-R008.json), [LLM interactions](../../../ai-logs/final-audit/scenario-07-R008-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-07-R008-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 8. R013: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 3.095s. Final agent completion: 3.098s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile.
- Evidence: [scenario-08-R013.json](scenario-08-R013.json), [LLM interactions](../../../ai-logs/final-audit/scenario-08-R013-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-08-R013-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 9. R014: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 2.545s. Final agent completion: 2.548s.
- Persisted verified dispute amounts: ['10']. Provider-confirmed: ₹10. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-09-R014.json](scenario-09-R014.json), [LLM interactions](../../../ai-logs/final-audit/scenario-09-R014-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-09-R014-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 10. R016: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 3.431s. Final agent completion: 3.435s.
- Persisted verified dispute amounts: ['425']. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger.
- Evidence: [scenario-10-R016.json](scenario-10-R016.json), [LLM interactions](../../../ai-logs/final-audit/scenario-10-R016-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-10-R016-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 11. R021: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: optional; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 3.576s. Final agent completion: 3.579s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips.
- Evidence: [scenario-11-R021.json](scenario-11-R021.json), [LLM interactions](../../../ai-logs/final-audit/scenario-11-R021-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-11-R021-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 12. R022: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: optional; actual agent escalations: 1, all queue escalations: 1.
- Original webhook latency: 2.114s. Final agent completion: 2.121s.
- Persisted verified dispute amounts: [None]. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-12-R022.json](scenario-12-R022.json), [LLM interactions](../../../ai-logs/final-audit/scenario-12-R022-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-12-R022-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 13. R024: single message

- Rider turns: 1. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.565s. Final agent completion: 13.864s.
- Persisted verified dispute amounts: ['150']. Provider-confirmed: ₹150. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-13-R024.json](scenario-13-R024.json), [LLM interactions](../../../ai-logs/final-audit/scenario-13-R024-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-13-R024-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 14. R025: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 1.815s. Final agent completion: 1.817s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-14-R025.json](scenario-14-R025.json), [LLM interactions](../../../ai-logs/final-audit/scenario-14-R025-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-14-R025-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 15. R007: single message

- Rider turns: 1. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.562s. Final agent completion: 9.646s.
- Persisted verified dispute amounts: ['34']. Provider-confirmed: ₹34. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-15-R007.json](scenario-15-R007.json), [LLM interactions](../../../ai-logs/final-audit/scenario-15-R007-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-15-R007-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.
- R007 decision and payment execution both passed here: one ₹34 AUTO intent, saved SUCCEEDED state and matching provider payout/reference. This isolated result does not repair or certify any older development NEEDS_REVIEW intent. The original webhook still deferred.

## 16. R031: single message

- Rider turns: 1. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.557s. Final agent completion: 9.654s.
- Persisted verified dispute amounts: ['22']. Provider-confirmed: ₹22. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-16-R031.json](scenario-16-R031.json), [LLM interactions](../../../ai-logs/final-audit/scenario-16-R031-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-16-R031-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 17. R009: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 2.038s. Final agent completion: 2.041s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-17-R009.json](scenario-17-R009.json), [LLM interactions](../../../ai-logs/final-audit/scenario-17-R009-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-17-R009-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 18. R026: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 2.293s. Final agent completion: 2.296s.
- Persisted verified dispute amounts: ['32']. Provider-confirmed: ₹32. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-18-R026.json](scenario-18-R026.json), [LLM interactions](../../../ai-logs/final-audit/scenario-18-R026-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-18-R026-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 19. R033: single message

- Rider turns: 1. LLM invocations: 3. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.561s. Final agent completion: 23.979s.
- Persisted verified dispute amounts: ['176']. Provider-confirmed: ₹176. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-19-R033.json](scenario-19-R033.json), [LLM interactions](../../../ai-logs/final-audit/scenario-19-R033-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-19-R033-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 20. R034: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 1.836s. Final agent completion: 1.838s.
- Persisted verified dispute amounts: ['249']. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger.
- Evidence: [scenario-20-R034.json](scenario-20-R034.json), [LLM interactions](../../../ai-logs/final-audit/scenario-20-R034-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-20-R034-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 21. R035: single message

- Rider turns: 1. LLM invocations: 2. Expected escalation: no; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 5.561s. Final agent completion: 9.707s.
- Persisted verified dispute amounts: ['25']. Provider-confirmed: ₹25. Conditional worker result: PASS.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status, payswift_authorization_ledger, payswift_request_started, payswift_dispatch_ledger, payswift_request_result.
- Evidence: [scenario-21-R035.json](scenario-21-R035.json), [LLM interactions](../../../ai-logs/final-audit/scenario-21-R035-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-21-R035-traces.json).
- Result: FAIL strict end-to-end; PASS eventual financial/semantic outcome.
- Delivery defect: at least one original HTTP 200 reply was only a processing acknowledgment. Harness waited for persisted completion and explicitly replayed the same message ID to retrieve the final reply; a vendor that stops retrying on 2xx has no equivalent final-answer delivery path.

## 22. R036: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: optional; actual agent escalations: 1, all queue escalations: 1.
- Original webhook latency: 1.899s. Final agent completion: 1.901s.
- Persisted verified dispute amounts: ['0']. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-22-R036.json](scenario-22-R036.json), [LLM interactions](../../../ai-logs/final-audit/scenario-22-R036-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-22-R036-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 23. R028: single message

- Rider turns: 1. LLM invocations: 1. Expected escalation: optional; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 4.190s. Final agent completion: 4.193s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile, get_rider_trips, get_payout_history, reconcile_dispute, get_payment_status.
- Evidence: [scenario-23-R028.json](scenario-23-R028.json), [LLM interactions](../../../ai-logs/final-audit/scenario-23-R028-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-23-R028-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.

## 24. R037: single message

- Rider turns: 1. LLM invocations: 0. Expected escalation: optional; actual agent escalations: 0, all queue escalations: 0.
- Original webhook latency: 0.090s. Final agent completion: 0.093s.
- Persisted verified dispute amounts: []. Provider-confirmed: ₹0. Conditional worker result: NOT APPLICABLE.
- Tools observed: get_rider_profile.
- Evidence: [scenario-24-R037.json](scenario-24-R037.json), [LLM interactions](../../../ai-logs/final-audit/scenario-24-R037-llm.json), [chronological traces](../../../ai-logs/final-audit/scenario-24-R037-traces.json).
- Result: PASS strict end-to-end; PASS eventual financial/semantic outcome.
- No LLM invocation: the application input-policy guard rejected the injection before model execution. Empty LLM log records zero calls; this passes safety routing but does not satisfy literal 24/24 live-model invocation coverage.
