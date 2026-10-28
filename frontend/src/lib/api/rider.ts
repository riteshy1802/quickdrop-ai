import type {
  Conversation,
  Dispute,
  Message,
  PostMessageRequest,
  PostMessageResponse,
  Rider,
  Scenario,
} from "@/types/rider";
import {
  makeScenario,
  mockRiders,
  scenarioLabels,
  seedAssignments,
} from "@/lib/mock/rider-data";

export type Thread = {
  conversation: Conversation;
  messages: Message[];
  disputes: Dispute[];
};
const wait = (ms = 240) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

// Session-only mock transport. No HTTP requests, persistence, or payment calls.
export function createMockRiderApi(latency = 240) {
  const threads = new Map<string, Thread>(
    seedAssignments.map(([id, rider, scenario]) => [
      id,
      makeScenario(id, rider, scenario),
    ]),
  );
  const received = new Map<
    string,
    { fingerprint: string; response: PostMessageResponse }
  >();
  let sequence = 0;
  const listeners = new Set<() => void>();
  function notify() {
    for (const listener of listeners) listener();
  }
  const clone = <T>(value: T): T => structuredClone(value);
  function own(riderId: string, conversationId: string) {
    const thread = threads.get(conversationId);
    if (!thread || thread.conversation.rider_id !== riderId)
      throw new Error("Conversation not found for this demo rider.");
    return thread;
  }
  return {
    // Shared demo-only transport seam used by the Ops adapter. Never an authorization boundary.
    inspectWorkspace() {
      return clone([...threads.values()]);
    },
    updateWorkspace(id: string, update: (thread: Thread) => void) {
      const thread = threads.get(id);
      if (!thread) throw new Error("Conversation not found.");
      update(thread);
      notify();
    },
    insertDemoThread(thread: Thread) {
      if (!threads.has(thread.conversation.id)) {
        threads.set(thread.conversation.id, clone(thread));
        notify();
      }
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async getRiders(): Promise<Rider[]> {
      await wait(latency);
      return clone(mockRiders);
    },
    async getConversations(riderId: string): Promise<Conversation[]> {
      await wait(latency);
      return clone(
        [...threads.values()]
          .map((t) => t.conversation)
          .filter((c) => c.rider_id === riderId)
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
      );
    },
    async getConversation(riderId: string, id: string) {
      await wait(latency);
      return clone(own(riderId, id).conversation);
    },
    async getMessages(riderId: string, id: string) {
      await wait(latency);
      return clone(
        own(riderId, id).messages.filter(
          (message) => message.visibility !== "INTERNAL",
        ),
      );
    },
    async getDisputes(riderId: string, id: string) {
      await wait(latency);
      return clone(own(riderId, id).disputes);
    },
    async createConversation(
      riderId: string,
      scenario: Scenario | null = null,
    ) {
      await wait(latency);
      if (!mockRiders.some((r) => r.id === riderId))
        throw new Error("Unknown demo rider.");
      const id = `QD-DEMO-${++sequence}`;
      const now = new Date().toISOString();
      const thread: Thread = scenario
        ? makeScenario(id, riderId, scenario, now)
        : {
            conversation: {
              id,
              rider_id: riderId,
              title: "New conversation",
              status: "OPEN",
              handler: "AI",
              updated_at: now,
              last_message: "Start by describing a payout issue.",
              scenario: null,
            },
            messages: [],
            disputes: [],
          };
      threads.set(id, thread);
      notify();
      return clone(thread.conversation);
    },
    // UI conversation context is separate from the assignment webhook body.
    async postMessage(
      request: PostMessageRequest,
      context: { conversation_id: string; simulateFailure?: boolean },
    ): Promise<PostMessageResponse> {
      const thread = own(request.rider_id, context.conversation_id);
      if (!request.text.trim()) throw new Error("Please enter a message.");
      const fingerprint = JSON.stringify([context.conversation_id, request]);
      const existing = received.get(request.message_id);
      if (existing) {
        if (existing.fingerprint !== fingerprint)
          throw new Error("Message ID is already in use.");
        return clone(existing.response);
      }
      await wait(latency * 4);
      if (context.simulateFailure) {
        throw new Error(
          "Simulated connection error. Your message was not sent. Please retry.",
        );
      }
      const completed = received.get(request.message_id);
      if (completed) {
        if (completed.fingerprint !== fingerprint)
          throw new Error("Message ID is already in use.");
        return clone(completed.response);
      }
      const text = request.text.trim();
      const scenario = thread.conversation.scenario;
      const dispute = thread.disputes[0];
      const scenarioReply =
        dispute?.status === "REJECTED"
          ? dispute.explanation
          : dispute?.payment?.status === "SUCCEEDED"
            ? `The sample ₹${dispute.payment.amount_rupees} adjustment has an explicit simulated provider confirmation. No real money moved.`
            : dispute?.payment
              ? `The sample ₹${dispute.payment.amount_rupees} adjustment is ${dispute.payment.status.toLowerCase().replaceAll("_", " ")}. This does not confirm settlement. No real payment is being made.`
              : (dispute?.explanation ??
                "This sample needs more information before any payout decision.");
      const reply =
        thread.conversation.handler === "OPS"
          ? "Your message has been received. Human Support will respond in this demo workspace."
          : scenario
            ? scenarioReply
            : thread.messages.length === 0
              ? "Bilkul, main help kar sakta hoon. Please share the trip ID, date, and what looks wrong with the payout. You can write in English, हिन्दी, or Hinglish. This demo does not check real records."
              : "Thanks, I’ve kept those details in this demo conversation. The live agent is not connected yet, so I can’t verify this claim or move money. Use a sample scenario to explore a complete resolution.";
      thread.messages.push(
        {
          id: request.message_id,
          conversation_id: context.conversation_id,
          sender: "RIDER",
          text,
          created_at: request.received_at,
          delivery: "DELIVERED",
        },
        {
          id: `${request.message_id}-reply`,
          conversation_id: context.conversation_id,
          sender: "AI",
          system_notice: thread.conversation.handler === "OPS",
          text: reply,
          created_at: new Date().toISOString(),
        },
      );
      thread.conversation.updated_at = new Date().toISOString();
      thread.conversation.last_message = reply;
      if (!scenario && thread.conversation.title === "New conversation")
        thread.conversation.title = text.slice(0, 42);
      notify();
      const response = { reply };
      received.set(request.message_id, { fingerprint, response });
      return clone(response);
    },
  };
}
export const riderApi = createMockRiderApi();
export { scenarioLabels };
