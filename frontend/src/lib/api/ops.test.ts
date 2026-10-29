import assert from "node:assert/strict";
import test from "node:test";
import { createMockOpsApi, sanitizeTraceJson } from "./ops.mock";
import { createMockRiderApi } from "./rider.mock";
import type { OpsUser } from "@/types/ops";
const operator: OpsUser = {
  id: "demo-ops",
  name: "Demo Operator",
  email: "ops@quickdrop.demo",
  role: "Demo operator",
};
function workspace() {
  const rider = createMockRiderApi(0);
  return { rider, ops: createMockOpsApi(rider) };
}

test("A: takeover, reply, private note, and handoff use the same Rider thread", async () => {
  const { rider, ops } = workspace();
  await ops.getSnapshot();
  await ops.act({ type: "takeover", id: "QD-1018" }, operator);
  assert.equal((await rider.getConversation("R017", "QD-1018")).handler, "OPS");
  const opsBefore = (await rider.getMessages("R017", "QD-1018")).filter(
    (m) => m.sender === "OPS",
  ).length;
  await rider.postMessage(
    {
      message_id: "wamid.ops-test",
      rider_id: "R017",
      text: "Please help",
      received_at: new Date().toISOString(),
    },
    { conversation_id: "QD-1018" },
  );
  assert.equal(
    (await rider.getMessages("R017", "QD-1018")).filter(
      (m) => m.sender === "OPS",
    ).length,
    opsBefore,
  );
  await ops.act(
    { type: "reply", id: "QD-1018", text: "I am reviewing your trip details." },
    operator,
  );
  assert.equal(
    (await rider.getMessages("R017", "QD-1018")).at(-1)?.text,
    "I am reviewing your trip details.",
  );
  const before = await rider.getConversation("R017", "QD-1018");
  await ops.act(
    { type: "note", id: "QD-1018", text: "Private operator evidence" },
    operator,
  );
  assert.ok(
    !(await rider.getMessages("R017", "QD-1018")).some(
      (m) => m.text === "Private operator evidence",
    ),
  );
  assert.equal(
    (await rider.getConversation("R017", "QD-1018")).last_message,
    before.last_message,
  );
  assert.ok(
    (await ops.getSnapshot()).threads
      .find((t) => t.conversation.id === "QD-1018")
      ?.messages.some((m) => m.visibility === "INTERNAL"),
  );
  await ops.act({ type: "handoff", id: "QD-1018" }, operator);
  assert.equal((await rider.getConversation("R017", "QD-1018")).handler, "AI");
});
test("B: approving ₹425 closes the queue item and authorizes an unsettled intent", async () => {
  const { rider, ops } = workspace();
  const initial = await ops.getSnapshot();
  const item = initial.cases.find((c) => c.id === "CASE-QD-1017")!;
  assert.equal(item.amount_rupees, 425);
  const updated = await ops.act({ type: "approve", id: item.id }, operator);
  assert.equal(updated.cases.find((c) => c.id === item.id)?.status, "APPROVED");
  const payout = updated.payouts.find(
    (p) => p.conversation_id === item.conversation_id,
  )!;
  assert.equal(payout.status, "PENDING");
  assert.equal(payout.amount_rupees, 425);
  assert.equal(payout.initiation, "HUMAN_APPROVED");
  assert.equal(payout.provider_id, null);
  assert.ok(
    updated.traces.some(
      (t) =>
        t.type === "approval_decision" &&
        t.conversation_id === item.conversation_id,
    ),
  );
  assert.equal(
    (await rider.getDisputes("R017", "QD-1017"))[0].payment?.status,
    "PENDING",
  );
  await assert.rejects(
    ops.act({ type: "approve", id: item.id }, operator),
    /already been reviewed/,
  );
  await assert.rejects(
    ops.act({ type: "reconcile", id: payout.id }, operator),
    /not been submitted/,
  );
});
test("C: rejection requires a reason and records it without authorizing money", async () => {
  const { ops } = workspace();
  await ops.getSnapshot();
  await assert.rejects(
    ops.act({ type: "reject", id: "CASE-QD-1021", reason: " " }, operator),
    /reason is required/,
  );
  assert.equal(
    (await ops.getSnapshot()).cases.find((c) => c.id === "CASE-QD-1021")
      ?.status,
    "PENDING",
  );
  const result = await ops.act(
    {
      type: "reject",
      id: "CASE-QD-1021",
      reason: "Evidence does not support the adjustment.",
    },
    operator,
  );
  assert.equal(
    result.cases.find((c) => c.id === "CASE-QD-1021")?.status,
    "REJECTED",
  );
  assert.ok(!result.payouts.some((p) => p.conversation_id === "QD-1021"));
  assert.ok(
    result.traces.some(
      (t) => t.type === "approval_decision" && t.conversation_id === "QD-1021",
    ),
  );
});
test("D: unknown payment is reconciled against explicit mock provider evidence", async () => {
  const { ops } = workspace();
  const data = await ops.getSnapshot();
  const payout = data.payouts.find((p) => p.id === "PAY-QD-1004")!;
  assert.equal(payout.status, "UNKNOWN");
  assert.equal(payout.provider_id, null);
  assert.equal(payout.attempts[0].http_status, null);
  const result = await ops.act({ type: "reconcile", id: payout.id }, operator);
  const observed = result.payouts.find((p) => p.id === payout.id)!;
  assert.equal(observed.status, "SUCCEEDED");
  assert.equal(observed.provider_status, "SUCCEEDED");
  assert.ok(observed.provider_id);
  assert.match(observed.reconciliation_outcome, /explicitly reports succeeded/);
  assert.ok(
    result.traces.some(
      (t) => t.type === "reconciliation" && t.payment_id === payout.id,
    ),
  );
});
test("E: trace events keep assignment categories and chronological ordering is recoverable", async () => {
  const { ops } = workspace();
  const data = await ops.getSnapshot();
  const events = data.traces
    .filter((t) => t.conversation_id === "QD-1003")
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  assert.deepEqual(
    events
      .filter((t) =>
        ["message_in", "tool_call", "decision", "reply"].includes(t.type),
      )
      .map((t) => t.type),
    ["message_in", "tool_call", "decision", "reply"],
  );
  assert.ok(events.every((t) => t.correlation_id === "trace-QD-1003"));
  assert.deepEqual(
    sanitizeTraceJson({
      headers: { authorization: "secret", safe: "visible" },
      api_key: "hidden",
      nested: [{ password: "hidden" }],
    }),
    {
      headers: { authorization: "[REDACTED]", safe: "visible" },
      api_key: "[REDACTED]",
      nested: [{ password: "[REDACTED]" }],
    },
  );
});
test("escalation resolution never pays and AI-mode human replies are rejected", async () => {
  const { ops } = workspace();
  const initial = await ops.getSnapshot();
  await assert.rejects(
    ops.act(
      { type: "reply", id: "QD-1003", text: "Reply without takeover" },
      operator,
    ),
    /Take over/,
  );
  await assert.rejects(
    ops.act({ type: "approve", id: "CASE-QD-1018" }, operator),
    /cannot authorize money/,
  );
  const result = await ops.act(
    { type: "resolve_case", id: "CASE-QD-1018" },
    operator,
  );
  assert.equal(
    result.cases.find((c) => c.id === "CASE-QD-1018")?.status,
    "RESOLVED",
  );
  assert.equal(result.payouts.length, initial.payouts.length);
  assert.equal(
    result.threads.find((t) => t.conversation.id === "QD-1018")?.disputes[0]
      .payment,
    null,
  );
});
