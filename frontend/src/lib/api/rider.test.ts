import assert from "node:assert/strict";
import test from "node:test";
import { createMockRiderApi } from "./rider";
import type { PostMessageRequest } from "@/types/rider";
const request = (
  id = "wamid.test.1",
  riderId = "R003",
  text = "Bhai surge nahi mila\n20 September wala",
): PostMessageRequest => ({
  message_id: id,
  rider_id: riderId,
  text,
  received_at: "2026-09-22T09:05:00+05:30",
});

test("rider histories are isolated and cross-rider access is rejected", async () => {
  const api = createMockRiderApi(0);
  for (const rider of await api.getRiders())
    assert.ok(
      (await api.getConversations(rider.id)).every(
        (c) => c.rider_id === rider.id,
      ),
    );
  await assert.rejects(api.getMessages("R001", "QD-1003"), /not found/);
  await assert.rejects(
    api.postMessage(request("wamid.forged", "R001"), {
      conversation_id: "QD-1003",
    }),
    /not found/,
  );
});
test("failed sends preserve history and the same request can be retried", async () => {
  const api = createMockRiderApi(0),
    body = request();
  const before = await api.getMessages("R003", "QD-1003");
  await assert.rejects(
    api.postMessage(body, {
      conversation_id: "QD-1003",
      simulateFailure: true,
    }),
    /Simulated connection/,
  );
  assert.deepEqual(await api.getMessages("R003", "QD-1003"), before);
  const response = await api.postMessage(body, { conversation_id: "QD-1003" });
  assert.deepEqual(Object.keys(response), ["reply"]);
  assert.deepEqual(Object.keys(body).sort(), [
    "message_id",
    "received_at",
    "rider_id",
    "text",
  ]);
  assert.equal(
    (await api.getMessages("R003", "QD-1003")).length,
    before.length + 2,
  );
});
test("concurrent duplicate deliveries add one message pair and reject reused IDs", async () => {
  const api = createMockRiderApi(0),
    body = request();
  const before = await api.getMessages("R003", "QD-1003");
  const [a, b] = await Promise.all([
    api.postMessage(body, { conversation_id: "QD-1003" }),
    api.postMessage(body, { conversation_id: "QD-1003" }),
  ]);
  assert.deepEqual(a, b);
  assert.equal(
    (await api.getMessages("R003", "QD-1003")).length,
    before.length + 2,
  );
  await assert.rejects(
    api.postMessage(
      { ...body, text: "Different message" },
      { conversation_id: "QD-1003" },
    ),
    /already in use/,
  );
});
test("new conversations retain multi-turn text without modifying another rider", async () => {
  const api = createMockRiderApi(0),
    conversation = await api.createConversation("R003");
  const other = await api.getMessages("R001", "QD-1001");
  assert.deepEqual(await api.getMessages("R003", conversation.id), []);
  await api.postMessage(request(), { conversation_id: conversation.id });
  await api.postMessage(request("wamid.test.2", "R003", "मेरा भुगतान जाँचें"), {
    conversation_id: conversation.id,
  });
  const messages = await api.getMessages("R003", conversation.id);
  assert.equal(messages.length, 4);
  assert.equal(messages[0].text, request().text);
  assert.equal(messages[2].text, "मेरा भुगतान जाँचें");
  assert.match(messages[3].text, /live agent is not connected/);
  assert.deepEqual(await api.getMessages("R001", "QD-1001"), other);
});
test("large claims await approval and pending payments do not become successful on send", async () => {
  const api = createMockRiderApi(0);
  const [large] = await api.getDisputes("R017", "QD-1017");
  assert.equal(large.verified_difference_rupees, 425);
  assert.equal(large.approved_adjustment_rupees, null);
  assert.equal(large.payment?.status, "AWAITING_APPROVAL");
  await api.postMessage(request(), { conversation_id: "QD-1004" });
  const [pending] = await api.getDisputes("R003", "QD-1004");
  assert.equal(pending.payment?.status, "RECONCILIATION_PENDING");
  const [noOwed] = await api.getDisputes("R001", "QD-1002");
  assert.equal(noOwed.verified_difference_rupees, 0);
  assert.equal(noOwed.payment, null);
});
test("human handling preserves the transfer notice without inventing new OPS replies", async () => {
  const api = createMockRiderApi(0);
  await api.postMessage(request("wamid.ops", "R017", "Please check again"), {
    conversation_id: "QD-1018",
  });
  const messages = await api.getMessages("R017", "QD-1018");
  assert.ok(
    messages.some(
      (m) =>
        m.system_notice &&
        m.text ===
          "Your conversation has been transferred to our support team.",
    ),
  );
  assert.equal(messages.at(-1)?.sender, "AI");
  assert.equal(messages.at(-1)?.system_notice, true);
  assert.equal(
    messages.filter((message) => message.sender === "OPS").length,
    1,
  );
});
test("adapter data is returned as detached snapshots", async () => {
  const api = createMockRiderApi(0);
  const messages = await api.getMessages("R003", "QD-1003");
  messages[0].text = "Mutated outside adapter";
  assert.notEqual(
    (await api.getMessages("R003", "QD-1003"))[0].text,
    messages[0].text,
  );
});
