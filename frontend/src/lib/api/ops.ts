import type {
  AgentTrace,
  Json,
  OpsAction,
  OpsQueueItem,
  OpsSnapshot,
  OpsUser,
} from "@/types/ops";
import type { Message } from "@/types/rider";
import { allPages, post, request, type Page } from "./client";
import {
  mapConversation,
  mapDispute,
  mapPayout,
  type ConversationRecord,
  type DisputeRecord,
  type PayoutRecord,
  type RiderRecord,
} from "./contracts";
interface CaseRecord {
  id: string;
  conversation_id: string;
  dispute_id: string;
  rider_id: string;
  type: "approval" | "escalation";
  status: OpsQueueItem["status"];
  amount: string | null;
  claimed_amount: string | null;
  reason: string;
  created_at: string;
  assigned_to: string | null;
  resolved_at: string | null;
  decision_note: string | null;
}
interface TraceRecord {
  id: string;
  at: string;
  type: AgentTrace["type"];
  rider_id: string;
  conversation_id: string;
  name: string;
  input: Json;
  output: Json;
}
interface Detail extends ConversationRecord {
  messages: Page<Message>;
  disputes: Page<DisputeRecord>;
}
export function sanitizeTraceJson(value: Json): Json {
  if (Array.isArray(value)) return value.map(sanitizeTraceJson);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [
        k,
        /password|secret|token|authorization|cookie|api.?key/i.test(k)
          ? "[REDACTED]"
          : sanitizeTraceJson(v),
      ]),
    );
  return value;
}
export const opsApi = {
  async getSnapshot(): Promise<OpsSnapshot> {
    const [riders, conversations, cases, payouts, traces] = await Promise.all([
      allPages<RiderRecord>("/ui/riders"),
      allPages<ConversationRecord>("/ui/ops/conversations"),
      allPages<CaseRecord>("/ui/ops/cases"),
      allPages<PayoutRecord>("/ui/ops/payouts"),
      allPages<TraceRecord>("/ui/ops/traces"),
    ]);
    const threads = await Promise.all(
      conversations.map(async (c) => {
        const messages: Message[] = [],
          disputes: DisputeRecord[] = [];
        for (let offset = 0; ; offset += 100) {
          const d = await request<Detail>(
            `/ui/ops/conversations/${c.id}?limit=100&offset=${offset}`,
          );
          messages.push(...d.messages.items);
          disputes.push(...d.disputes.items);
          if (offset + 100 >= Math.max(d.messages.total, d.disputes.total))
            break;
        }
        return {
          conversation: mapConversation(c),
          messages,
          disputes: disputes.map((d) => mapDispute(d, payouts)),
        };
      }),
    );
    return {
      riders: riders.map((r) => ({
        id: r.rider_id,
        name: r.name,
        city: r.city,
        demo: true,
      })),
      threads,
      cases: cases.map((c) => ({
        ...c,
        kind: c.type === "approval" ? "APPROVAL" : "ESCALATION",
        amount_rupees: c.amount === null ? null : Number(c.amount),
        claimed_rupees:
          c.claimed_amount === null ? null : Number(c.claimed_amount),
        category: c.type,
        reviewed_at: c.resolved_at,
        rejection_reason:
          c.status === "REJECTED" ? (c.decision_note ?? undefined) : undefined,
        // CaseResponse exposes no persisted checklist. The UI must show unavailable,
        // and approval remains a fresh server-side financial verification.
        checks: [],
      })),
      payouts: payouts.map((p) => {
        const mapped = mapPayout(p);
        mapped.attempts = traces
          .filter(
            (t) =>
              t.name === "payswift_request_result" &&
              t.input &&
              typeof t.input === "object" &&
              !Array.isArray(t.input) &&
              t.input.intent_id === p.id,
          )
          .map((t, index) => {
            const output =
              t.output &&
              typeof t.output === "object" &&
              !Array.isArray(t.output)
                ? t.output
                : {};
            const input =
              t.input && typeof t.input === "object" && !Array.isArray(t.input)
                ? t.input
                : {};
            const failed =
              ["UNKNOWN", "FAILED", "NEEDS_REVIEW"].includes(
                String(output.status),
              ) ||
              (typeof output.http_status === "number" &&
                output.http_status >= 400);
            return {
              number:
                typeof input.attempt === "number" ? input.attempt : index + 1,
              created_at: t.at,
              http_status:
                typeof output.http_status === "number"
                  ? output.http_status
                  : null,
              duration_ms: null,
              result: String(output.status ?? "Recorded"),
              retry_scheduled: !!output.next_retry_at,
              error_category:
                failed && typeof output.outcome === "string"
                  ? output.outcome
                  : null,
            };
          });
        mapped.lifecycle.push(
          ...traces
            .filter(
              (t) =>
                t.input &&
                typeof t.input === "object" &&
                !Array.isArray(t.input) &&
                t.input.intent_id === p.id,
            )
            .map((t) => ({ name: t.name.replaceAll("_", " "), at: t.at })),
        );
        return mapped;
      }),
      traces: traces.map((t) => ({
        ...t,
        created_at: t.at,
        status: t.type === "error" ? "ERROR" : "OK",
        correlation_id: t.conversation_id,
        input: sanitizeTraceJson(t.input),
        output: sanitizeTraceJson(t.output),
        duration_ms: null,
      })),
      notifications: [],
    };
  },
  async act(action: OpsAction, operator: OpsUser) {
    void operator;
    if (action.type === "read_notification")
      throw new Error("No server notification to acknowledge.");
    if (action.type === "reconcile")
      await post(`/ui/ops/payouts/${action.id}/reconcile`);
    else if (action.type === "reply" || action.type === "note")
      await post(
        `/ui/ops/conversations/${action.id}/${action.type === "reply" ? "messages" : "notes"}`,
        { text: action.text, client_request_id: action.client_request_id },
      );
    else if (
      action.type === "takeover" ||
      action.type === "handoff" ||
      action.type === "resolve_conversation"
    )
      await post(
        `/ui/ops/conversations/${action.id}/${action.type === "resolve_conversation" ? "resolve" : action.type}`,
        action.type === "resolve_conversation"
          ? { reason: action.reason }
          : undefined,
      );
    else
      await post(
        `/ui/ops/cases/${action.id}/${action.type === "resolve_case" ? "resolve" : action.type}`,
        action.type === "reject" || action.type === "resolve_case"
          ? { reason: action.reason }
          : undefined,
      );
  },
};
