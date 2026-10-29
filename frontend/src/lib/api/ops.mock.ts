import { createMockRiderApi, riderApi } from "./rider.mock";
import { makeScenario, mockRiders } from "@/lib/mock/rider-data";
import type {
  AgentTrace,
  Json,
  OpsAction,
  OpsNotification,
  OpsPayout,
  OpsQueueItem,
  OpsSnapshot,
  OpsUser,
  PolicyCheck,
} from "@/types/ops";
import type { PaymentIntent } from "@/types/rider";
const pause = () => new Promise<void>((resolve) => setTimeout(resolve, 160));
const stamp = () => new Date().toISOString();
const baseTime = "2026-09-22T03:35:00.000Z";
const safe = (value: Json): Json =>
  Array.isArray(value)
    ? value.map(safe)
    : value && typeof value === "object"
      ? Object.fromEntries(
          Object.entries(value).map(([key, v]) => [
            key,
            /password|secret|token|authorization|cookie|api.?key/i.test(key)
              ? "[REDACTED]"
              : safe(v),
          ]),
        )
      : value;
export { safe as sanitizeTraceJson };
export function createMockOpsApi(shared = createMockRiderApi(0)) {
  const cases = new Map<string, OpsQueueItem>();
  const payments = new Map<string, Omit<OpsPayout, keyof PaymentIntent>>();
  const ledger = new Map<string, "SUCCEEDED" | "UNKNOWN" | "FAILED">();
  const traces: AgentTrace[] = [];
  const notifications: OpsNotification[] = [];
  let initialized = false;
  let sequence = 0;
  const tracedMessages = new Set<string>();
  function trace(
    threadId: string,
    name: string,
    type: AgentTrace["type"],
    input: Json = {},
    output: Json = {},
    status: AgentTrace["status"] = "OK",
    at = stamp(),
    paymentId?: string,
  ) {
    const thread = shared
      .inspectWorkspace()
      .find((t) => t.conversation.id === threadId);
    if (!thread) return;
    traces.push({
      id: `EVT-${++sequence}`,
      created_at: at,
      type,
      rider_id: thread.conversation.rider_id,
      conversation_id: threadId,
      dispute_id: thread.disputes[0]?.id,
      payment_id: paymentId,
      name,
      status,
      correlation_id: `trace-${threadId}`,
      input: safe(input),
      output: safe(output),
      duration_ms: type === "tool_call" ? 24 : null,
    });
  }
  function notify(
    id: string,
    title: string,
    detail: string,
    href: string,
    at = stamp(),
  ) {
    if (!notifications.some((n) => n.id === id))
      notifications.push({
        id,
        title,
        detail,
        href,
        created_at: at,
        read: false,
      });
  }
  function prepare() {
    if (!initialized) {
      initialized = true;
      const extra = makeScenario("QD-1021", "R001", "large");
      shared.insertDemoThread(extra);
      const failed = makeScenario("QD-1022", "R003", "pending");
      failed.conversation.title = "Provider exception";
      failed.conversation.status = "PAYMENT_PENDING";
      if (failed.disputes[0].payment)
        failed.disputes[0].payment.status = "FAILED";
      failed.disputes[0].explanation =
        "Illustrative provider error; the last simulated ledger lookup confirms failure. Needs operator review.";
      failed.messages[failed.messages.length - 1].text =
        "This sample adjustment needs review after a provider error. No real payment was made.";
      shared.insertDemoThread(failed);
    }
    for (const {
      conversation: c,
      disputes,
      messages,
    } of shared.inspectWorkspace()) {
      for (const d of disputes) {
        const caseId = `CASE-${c.id}`;
        if (
          !cases.has(caseId) &&
          (d.policy === "OPS_APPROVAL" || c.scenario === "human")
        ) {
          const escalation = c.scenario === "human";
          const checks: PolicyCheck[] = [
            { label: "Rider identity matches", result: "PASSED" },
            {
              label: "Trip ownership verified",
              result: escalation ? "REVIEW" : "PASSED",
            },
            {
              label: "Within seven-day window at complaint time",
              result: "PASSED",
            },
            {
              label: "Deterministic amount verified",
              result: escalation ? "UNKNOWN" : "PASSED",
            },
            { label: "Duplicate payment check", result: "PASSED" },
            { label: "Daily auto-pay rule evaluated", result: "PASSED" },
            { label: "Provider settlement reconciled", result: "UNKNOWN" },
          ];
          cases.set(caseId, {
            id: caseId,
            conversation_id: c.id,
            dispute_id: d.id,
            rider_id: c.rider_id,
            kind: escalation ? "ESCALATION" : "APPROVAL",
            status: "PENDING",
            amount_rupees: d.verified_difference_rupees,
            claimed_rupees: d.verified_difference_rupees,
            reason: escalation
              ? "Trip details require human clarification"
              : "Verified amount exceeds ₹200",
            category: escalation ? "Ambiguous source data" : "Payment limit",
            created_at: c.updated_at,
            assigned_to: null,
            reviewed_at: null,
            checks,
          });
          notify(
            caseId,
            escalation ? "Escalation needs review" : "Approval awaiting review",
            `${c.rider_id} · ${d.type}`,
            `/ops/approvals/${caseId}`,
            c.updated_at,
          );
        }
        if (d.payment && !payments.has(d.payment.id)) {
          const p = d.payment;
          const succeeded = p.status === "SUCCEEDED",
            exception = c.id === "QD-1022",
            uncertain = p.status === "RECONCILIATION_PENDING";
          if (uncertain)
            shared.updateWorkspace(c.id, (thread) => {
              const payment = thread.disputes.find(
                (item) => item.id === d.id,
              )?.payment;
              if (payment) payment.status = "UNKNOWN";
            });
          const attempts = succeeded
            ? [
                {
                  number: 1,
                  created_at: baseTime,
                  http_status: 201,
                  duration_ms: 185,
                  result: "Provider confirmed success",
                  retry_scheduled: false,
                  error_category: null,
                },
              ]
            : exception
              ? [
                  {
                    number: 1,
                    created_at: baseTime,
                    http_status: 429,
                    duration_ms: 80,
                    result: "Rate limited",
                    retry_scheduled: true,
                    error_category: "RATE_LIMIT",
                  },
                  {
                    number: 2,
                    created_at: baseTime,
                    http_status: 503,
                    duration_ms: 140,
                    result: "Provider unavailable",
                    retry_scheduled: false,
                    error_category: "PROVIDER_5XX",
                  },
                  {
                    number: 3,
                    created_at: baseTime,
                    http_status: 200,
                    duration_ms: 120,
                    result: "Ledger lookup confirmed failed",
                    retry_scheduled: false,
                    error_category: null,
                  },
                ]
              : uncertain
                ? [
                    {
                      number: 1,
                      created_at: baseTime,
                      http_status: null,
                      duration_ms: 10000,
                      result: "Timeout; response unknown",
                      retry_scheduled: false,
                      error_category: "LOST_RESPONSE",
                    },
                  ]
                : [];
          const lifecycle = [
            { name: "Dispute verified", at: baseTime },
            { name: "Policy decision recorded", at: baseTime },
          ];
          if (p.status !== "AWAITING_APPROVAL")
            lifecycle.push(
              { name: "Payment authorized", at: baseTime },
              { name: "Intent persisted", at: baseTime },
            );
          if (attempts.length)
            lifecycle.push({
              name: "PaySwift request submitted",
              at: baseTime,
            });
          if (succeeded)
            lifecycle.push({ name: "Provider success observed", at: baseTime });
          payments.set(p.id, {
            rider_id: c.rider_id,
            conversation_id: c.id,
            initiation: "AUTO",
            created_at: baseTime,
            provider_id: succeeded ? `ps_demo_${c.id}` : null,
            provider_status: succeeded
              ? "SUCCEEDED"
              : exception
                ? "FAILED"
                : uncertain
                  ? "UNKNOWN"
                  : "NOT_SUBMITTED",
            reconciled_at: exception ? baseTime : null,
            reconciliation_outcome: exception
              ? "Sample ledger confirms failure"
              : "Not reconciled",
            attempts,
            lifecycle,
          });
          ledger.set(
            p.id,
            uncertain
              ? "SUCCEEDED"
              : exception
                ? "FAILED"
                : succeeded
                  ? "SUCCEEDED"
                  : "UNKNOWN",
          );
          if (uncertain || exception)
            notify(
              p.id,
              uncertain
                ? "Payment outcome is unknown"
                : "Payment requires review",
              `${c.rider_id} · sample provider exception`,
              `/ops/payouts/${p.id}`,
              baseTime,
            );
        }
      }
      if (!traces.some((t) => t.conversation_id === c.id)) {
        messages.forEach((message) => tracedMessages.add(message.id));
        const d = disputes[0];
        trace(
          c.id,
          "Message received",
          "message_in",
          { rider_id: c.rider_id },
          { accepted: true },
          "OK",
          baseTime,
        );
        if (d) {
          trace(
            c.id,
            "Trip and payout records retrieved",
            "tool_call",
            { trip_ids: d.items.map((i) => i.trip_id).filter(Boolean) },
            {
              expected_rupees: d.expected_rupees,
              historical_rupees: d.historical_rupees,
              source: "Illustrative fixture",
            },
            "OK",
            baseTime,
          );
          trace(
            c.id,
            "Policy decision recorded",
            "decision",
            { difference_rupees: d.verified_difference_rupees },
            { policy: d.policy, status: d.status },
            c.status === "HUMAN_HANDLING" ? "PENDING" : "OK",
            baseTime,
          );
        }
        for (const dispute of disputes) {
          if (dispute.payment)
            for (const attempt of payments.get(dispute.payment.id)?.attempts ??
              []) {
              trace(
                c.id,
                attempt.result,
                attempt.error_category
                  ? "error"
                  : attempt.result.includes("lookup")
                    ? "reconciliation"
                    : "payment_execution",
                { payment_id: dispute.payment.id, attempt: attempt.number },
                {
                  http_status: attempt.http_status,
                  result: attempt.result,
                  simulation: true,
                },
                attempt.error_category ? "ERROR" : "OK",
                baseTime,
                dispute.payment.id,
              );
            }
        }
        trace(
          c.id,
          "Rider response prepared",
          "reply",
          { conversation_id: c.id },
          { demo: true },
          "OK",
          baseTime,
        );
      }
      for (const message of messages) {
        if (tracedMessages.has(message.id)) continue;
        tracedMessages.add(message.id);
        if (message.visibility !== "INTERNAL" && !message.system_notice)
          trace(
            c.id,
            message.sender === "RIDER"
              ? "Rider message received"
              : "Support response recorded",
            message.sender === "RIDER" ? "message_in" : "reply",
            { message_id: message.id, sender: message.sender },
            { recorded: true },
            "OK",
            message.created_at,
          );
      }
      const incoming = messages.findLastIndex(
        (message) => message.sender === "RIDER",
      );
      const humanReply = messages.findLastIndex(
        (message) =>
          message.sender === "OPS" &&
          !message.system_notice &&
          message.visibility !== "INTERNAL",
      );
      const last = messages[incoming];
      if (c.handler === "OPS" && last && incoming > humanReply)
        notify(
          last.id,
          "New rider message",
          `${c.rider_id} is waiting for Human Support`,
          `/ops/conversations/${c.id}`,
        );
    }
  }
  function snapshot(): OpsSnapshot {
    prepare();
    const threads = shared.inspectWorkspace();
    const payouts = threads.flatMap((t) =>
      t.disputes.flatMap((d) =>
        d.payment ? [{ ...d.payment, ...payments.get(d.payment.id)! }] : [],
      ),
    );
    return structuredClone({
      riders: mockRiders,
      threads,
      cases: [...cases.values()],
      payouts,
      traces: [...traces].sort(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      ),
      notifications: [...notifications].sort(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      ),
    });
  }
  return {
    async getSnapshot() {
      await pause();
      return snapshot();
    },
    async act(action: OpsAction, operator: OpsUser) {
      await pause();
      prepare();
      const now = stamp();
      if (action.type === "read_notification") {
        const n = notifications.find((n) => n.id === action.id);
        if (!n) throw new Error("Notification not found.");
        n.read = true;
        return snapshot();
      }
      if (
        action.type === "approve" ||
        action.type === "reject" ||
        action.type === "assign" ||
        action.type === "resolve_case"
      ) {
        const item = cases.get(action.id);
        if (!item) throw new Error("Case not found.");
        if (["APPROVED", "REJECTED", "RESOLVED"].includes(item.status))
          throw new Error("This case has already been reviewed.");
        if (action.type === "approve" && item.kind !== "APPROVAL")
          throw new Error("Escalation resolution cannot authorize money.");
        if (action.type === "resolve_case" && item.kind !== "ESCALATION")
          throw new Error("Use the approval decision controls for this case.");
        if (action.type === "reject" && !action.reason?.trim())
          throw new Error("A rejection reason is required.");
        if (
          action.type === "approve" &&
          item.checks.slice(0, 6).some((check) => check.result !== "PASSED")
        )
          throw new Error("Required policy checks must pass before approval.");
        if (action.type === "approve") {
          const dispute = shared
            .inspectWorkspace()
            .find((t) => t.conversation.id === item.conversation_id)
            ?.disputes.find((d) => d.id === item.dispute_id);
          if (
            !dispute ||
            dispute.verified_difference_rupees !== item.amount_rupees ||
            item.amount_rupees === null || item.amount_rupees <= 0
          )
            throw new Error("Verified payment amount does not match the case.");
        }
        item.assigned_to = operator.name;
        if (action.type === "assign") item.status = "IN_REVIEW";
        else {
          item.status =
            action.type === "approve"
              ? "APPROVED"
              : action.type === "reject"
                ? "REJECTED"
                : "RESOLVED";
          item.reviewed_at = now;
          if (action.type === "reject")
            item.rejection_reason = action.reason!.trim();
          shared.updateWorkspace(item.conversation_id, (thread) => {
            const d = thread.disputes.find((d) => d.id === item.dispute_id)!;
            if (action.type === "approve") {
              if (
                d.verified_difference_rupees !== item.amount_rupees ||
                item.amount_rupees === null || item.amount_rupees <= 0
              )
                throw new Error(
                  "Verified payment amount does not match the case.",
                );
              d.approved_adjustment_rupees = item.amount_rupees;
              d.status = "PAYMENT_PENDING";
              d.payment = {
                id: d.payment?.id ?? `PAY-${thread.conversation.id}`,
                dispute_id: d.id,
                amount_rupees: item.amount_rupees,
                status: "PENDING",
                updated_at: now,
              };
              thread.conversation.status = "PAYMENT_PENDING";
              const meta = payments.get(d.payment.id);
              if (meta) {
                meta.initiation = "HUMAN_APPROVED";
                meta.lifecycle.push(
                  { name: "Human approval recorded", at: now },
                  { name: "Payment intent authorized", at: now },
                );
              }
            } else if (action.type === "reject") {
              d.approved_adjustment_rupees = 0;
              d.payment = null;
              d.status = "REJECTED";
              d.explanation = `Ops rejected the sample adjustment: ${action.reason!.trim()}`;
            } else {
              thread.conversation.status = "RESOLVED";
              thread.conversation.resolved_by = "OPS";
              d.status = "RESOLVED";
            }
          });
        }
        trace(
          item.conversation_id,
          `Case ${item.status.toLowerCase()}`,
          "approval_decision",
          { case_id: item.id, operator: operator.name },
          {
            status: item.status,
            reason: action.reason ?? null,
            amount_rupees: item.amount_rupees,
          },
          "OK",
          now,
        );
        return snapshot();
      }
      if (action.type === "reconcile") {
        const current = snapshot().payouts.find((p) => p.id === action.id);
        if (!current) throw new Error("Payment not found.");
        if (
          current.status === "AWAITING_APPROVAL" ||
          current.status === "PENDING"
        )
          throw new Error(
            "This payment has not been submitted to the provider.",
          );
        const observed = ledger.get(action.id) ?? "UNKNOWN",
          meta = payments.get(action.id)!;
        meta.reconciled_at = now;
        meta.provider_status = observed;
        meta.reconciliation_outcome =
          observed === "UNKNOWN"
            ? "No conclusive provider evidence; outcome stays unknown"
            : `Sample ledger explicitly reports ${observed.toLowerCase()}`;
        meta.attempts.push({
          number: meta.attempts.length + 1,
          created_at: now,
          http_status: 200,
          duration_ms: 120,
          result: `Reconciliation lookup: ${observed}`,
          retry_scheduled: false,
          error_category: null,
        });
        meta.lifecycle.push({
          name: `Reconciliation observed: ${observed}`,
          at: now,
        });
        if (observed === "SUCCEEDED")
          meta.provider_id = `ps_demo_${current.conversation_id}`;
        shared.updateWorkspace(current.conversation_id, (thread) => {
          const d = thread.disputes.find((d) => d.payment?.id === action.id)!;
          d.payment!.status = observed;
          d.payment!.updated_at = now;
          if (observed === "SUCCEEDED") {
            d.status = "RESOLVED";
            thread.conversation.status = "RESOLVED";
          }
        });
        trace(
          current.conversation_id,
          "Provider ledger reconciled",
          "reconciliation",
          { payment_id: action.id },
          { observed, simulation: true },
          observed === "UNKNOWN" ? "PENDING" : "OK",
          now,
          action.id,
        );
        return snapshot();
      }
      const thread = shared
        .inspectWorkspace()
        .find((t) => t.conversation.id === action.id);
      if (!thread) throw new Error("Conversation not found.");
      if (
        (action.type === "reply" || action.type === "note") &&
        !action.text.trim()
      )
        throw new Error("Enter a message before sending.");
      if (action.type === "reply" && thread.conversation.handler !== "OPS")
        throw new Error(
          "Take over the conversation before replying to the rider.",
        );
      shared.updateWorkspace(action.id, (t) => {
        let notice = "";
        if (action.type === "takeover") {
          t.conversation.handler = "OPS";
          t.conversation.assigned_operator = operator.name;
          t.conversation.status = "HUMAN_HANDLING";
          notice = `Human Support took over. Assigned to ${operator.name}.`;
        }
        if (action.type === "handoff") {
          t.conversation.handler = "AI";
          t.conversation.assigned_operator = null;
          t.conversation.status = "OPEN";
          notice = "Human Support handed this conversation back to AI.";
        }
        if (action.type === "resolve_conversation") {
          t.conversation.status = "RESOLVED";
          t.conversation.resolved_by = "OPS";
          notice = "Conversation marked resolved by Human Support.";
        }
        if (action.type === "reply" || action.type === "note")
          t.messages.push({
            id: `ops-message-${++sequence}`,
            conversation_id: action.id,
            sender: "OPS",
            text: action.text.trim(),
            created_at: now,
            visibility: action.type === "note" ? "INTERNAL" : "RIDER",
          });
        if (notice)
          t.messages.push({
            id: `ops-event-${++sequence}`,
            conversation_id: action.id,
            sender: "OPS",
            text: notice,
            created_at: now,
            system_notice: true,
            visibility: "RIDER",
          });
        t.conversation.updated_at = now;
        if (action.type !== "note")
          t.conversation.last_message =
            notice ||
            (action.type === "reply"
              ? action.text.trim()
              : t.conversation.last_message);
      });
      trace(
        action.id,
        action.type.replaceAll("_", " "),
        "operator_action",
        { operator: operator.name },
        { action: action.type },
        "OK",
        now,
      );
      return snapshot();
    },
  };
}
export const opsApi = createMockOpsApi(riderApi);
