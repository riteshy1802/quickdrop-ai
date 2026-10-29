import { ChatThread } from "@/components/rider/chat-thread";
import { act, cleanup, fireEvent, render, screen, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  emptyStream,
  parseEvent,
  reduceStream,
  type LiveEvent,
} from "@/lib/realtime/events";
import { listen } from "@/lib/realtime/connection";
import {
  useConversationEvents,
  useOpsEvents,
} from "@/hooks/realtime/use-events";

const conversation = "123e4567-e89b-42d3-a456-426614174000";
const run = "123e4567-e89b-42d3-a456-426614174001";
function event(
  kind: LiveEvent["event_type"],
  sequence = 1,
  data: LiveEvent["data"] = {},
): LiveEvent {
  return {
    event_id: crypto.randomUUID(),
    event_type: kind,
    conversation_id: conversation,
    rider_id: "R003",
    run_id: run,
    sequence,
    timestamp: new Date().toISOString(),
    data,
  };
}
class FakeSource extends EventTarget {
  static instances: FakeSource[] = [];
  closed = false;
  constructor(
    public url: string,
    public options?: EventSourceInit,
  ) {
    super();
    FakeSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  emit(event: LiveEvent) {
    this.dispatchEvent(
      new MessageEvent(event.event_type, { data: JSON.stringify(event) }),
    );
  }
}
beforeEach(() => {
  FakeSource.instances = [];
  vi.stubGlobal("EventSource", FakeSource);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("typed event reconciliation", () => {
  it("rejects invalid JSON and model payloads", () => {
    expect(parseEvent("invalid")).toBeNull();
    expect(parseEvent(JSON.stringify({ secret: "bad" }))).toBeNull();
    expect(
      parseEvent(
        JSON.stringify(
          event("agent.status", 1, { status: "checking_trip_records" }),
        ),
      )?.event_type,
    ).toBe("agent.status");
  });
  it("orders chunks, ignores old chunks and reconciles final persisted text", () => {
    const mid = crypto.randomUUID();
    let state = reduceStream(emptyStream, event("agent.started", 1));
    state = reduceStream(
      state,
      event("agent.message.delta", 2, { text: "Verified ", message_id: mid }),
    );
    state = reduceStream(
      state,
      event("agent.message.delta", 3, { text: "reply", message_id: mid }),
    );
    expect(state.text).toBe("Verified reply");
    expect(
      reduceStream(
        state,
        event("agent.message.delta", 2, { text: "duplicate" }),
      ).text,
    ).toBe(state.text);
    state = reduceStream(
      state,
      event("agent.message.completed", 4, {
        text: "Verified reply",
        message_id: mid,
      }),
    );
    expect(state.complete).toBe(true);
    expect(state.messageId).toBe(mid);
  });
  it("discards buffers on gaps and recovers using completed messages", () => {
    let state = reduceStream(emptyStream, event("agent.started", 1));
    state = reduceStream(
      state,
      event("agent.message.delta", 3, { text: "missing chunk" }),
    );
    expect(state.gap).toBe(true);
    expect(state.text).toBe("");
    state = reduceStream(
      state,
      event("agent.message.completed", 5, {
        text: "Authoritative reply",
        message_id: crypto.randomUUID(),
      }),
    );
    expect(state.text).toBe("Authoritative reply");
    expect(state.gap).toBe(false);
  });
  it("does not invent gaps around persisted state events", () => {
    let state = reduceStream(emptyStream, event("agent.started", 1));
    state = reduceStream(state, event("message.created", 2));
    state = reduceStream(
      state,
      event("agent.message.delta", 3, { text: "reply" }),
    );
    expect(state.gap).toBe(false);
  });
  it("clears AI text on human takeover and handback", () => {
    const state = reduceStream(
      emptyStream,
      event("agent.message.delta", 1, { text: "reply" }),
    );
    expect(reduceStream(state, event("conversation.takeover", 2)).text).toBe(
      "",
    );
    expect(reduceStream(state, event("conversation.handoff", 2)).text).toBe("");
  });
  it("deduplicates event IDs and removes every listener", () => {
    const source = new FakeSource("test"),
      receive = vi.fn();
    const close = listen(source, receive, vi.fn(), vi.fn(), vi.fn());
    const value = event("agent.status");
    source.emit(value);
    source.emit(value);
    expect(receive).toHaveBeenCalledTimes(1);
    close();
    source.emit(event("agent.status"));
    expect(receive).toHaveBeenCalledTimes(1);
    expect(source.closed).toBe(true);
  });
});

describe("live hooks", () => {
  it("opens one credentialed stream and closes it on rider switching", async () => {
    const { wrapper } = setup();
    const hook = renderHook(
      ({ rider }) => useConversationEvents(conversation, rider),
      { wrapper, initialProps: { rider: "R003" } },
    );
    expect(FakeSource.instances).toHaveLength(1);
    const old = FakeSource.instances[0];
    expect(old.options?.withCredentials).toBe(true);
    act(() => {
      old.dispatchEvent(new Event("ready"));
      old.emit(event("agent.status", 1, { status: "checking_trip_records" }));
    });
    expect(hook.result.current.stream.status).toBe("checking_trip_records");
    hook.rerender({ rider: "R005" });
    expect(old.closed).toBe(true);
    expect(hook.result.current.stream.text).toBe("");
    act(() =>
      old.emit(event("agent.message.delta", 2, { text: "Wrong rider" })),
    );
    expect(hook.result.current.stream.text).toBe("");
    hook.unmount();
    expect(FakeSource.instances[1].closed).toBe(true);
  });
  it("refetches saved state on reconnect and payment/case updates", async () => {
    const { wrapper, client } = setup(),
      invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(
      () => useConversationEvents(conversation, "R003"),
      { wrapper },
    );
    const source = FakeSource.instances[0];
    act(() => source.dispatchEvent(new Event("ready")));
    act(() =>
      source.emit(event("payment.status_changed", 1, { status: "SUCCEEDED" })),
    );
    expect(invalidate).toHaveBeenCalled();
    act(() => source.dispatchEvent(new Event("error")));
    expect(result.current.connection).toBe("reconnecting");
    act(() => source.dispatchEvent(new Event("ready")));
    await waitFor(() => expect(result.current.connection).toBe("connected"));
    expect(result.current.stream).toEqual(emptyStream);
  });
  it("shares one Ops connection per hook and signals expired sessions", () => {
    const { wrapper } = setup(),
      expired = vi.fn();
    window.addEventListener("quickdrop:session-expired", expired);
    const hook = renderHook(() => useOpsEvents(true), { wrapper });
    expect(FakeSource.instances).toHaveLength(1);
    act(() =>
      FakeSource.instances[0].dispatchEvent(new Event("session.expired")),
    );
    expect(expired).toHaveBeenCalledTimes(1);
    expect(FakeSource.instances[0].closed).toBe(true);
    hook.unmount();
    window.removeEventListener("quickdrop:session-expired", expired);
  });
  it("keeps subscriptions independent across two tabs", () => {
    const a = setup(),
      b = setup();
    const first = renderHook(
      () => useConversationEvents(conversation, "R003"),
      { wrapper: a.wrapper },
    );
    const second = renderHook(
      () => useConversationEvents(conversation, "R003"),
      { wrapper: b.wrapper },
    );
    const update = event("agent.status", 1, {
      status: "checking_trip_records",
    });
    act(() => FakeSource.instances.forEach((source) => source.emit(update)));
    expect(first.result.current.stream.status).toBe(
      second.result.current.stream.status,
    );
    first.unmount();
    expect(FakeSource.instances[1].closed).toBe(false);
  });
});

it("ignores delayed AI events from before a human control change", () => {
  let state = reduceStream(
    emptyStream,
    event("agent.started", 1, { control_version: 0 }),
  );
  state = reduceStream(
    state,
    event("conversation.takeover", 2, { control_version: 1 }),
  );
  state = reduceStream(
    state,
    event("conversation.handoff", 3, { control_version: 2 }),
  );
  state = reduceStream(
    state,
    event("agent.message.completed", 4, {
      text: "Stale reply",
      control_version: 0,
    }),
  );
  expect(state.text).toBe("");
  expect(state.controlVersion).toBe(2);
});

it("renders actual progress separately and reconciles an already saved reply once", () => {
  vi.useFakeTimers();
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
  const { wrapper } = setup();
  const id = crypto.randomUUID();
  try {
    render(
      <ChatThread
        riderId="R003"
        conversation={{
          id: conversation,
          rider_id: "R003",
          title: "Support",
          status: "OPEN",
          handler: "AI",
          updated_at: new Date().toISOString(),
          last_message: "Existing reply",
          scenario: null,
        }}
        messages={[
          {
            id,
            conversation_id: conversation,
            sender: "AI",
            text: "Existing reply",
            created_at: new Date().toISOString(),
          },
        ]}
        onScenario={vi.fn()}
        creating={false}
      />,
      { wrapper },
    );
    act(() => {
      FakeSource.instances[0].dispatchEvent(new Event("ready"));
      FakeSource.instances[0].emit(
        event("agent.status", 1, { status: "checking_trip_records" }),
      );
    });
    expect(screen.getByText("Checking trips")).toBeTruthy();
    expect(
      document.querySelector(".rider-message-bubble")?.textContent,
    ).not.toContain("Checking trips");
    expect(document.querySelector(".rider-investigation")?.hasAttribute("open")).toBe(true);
    act(() => FakeSource.instances[0].emit(event("agent.message.delta", 2, {
      message_id: id, text: "Existing ",
    })));
    expect(screen.queryByText("Existing reply")).toBeNull();
    expect(document.querySelector(".rider-message-bubble")?.textContent).not.toContain("Existing");
    act(() => vi.advanceTimersByTime(128));
    expect(document.querySelector(".rider-message-bubble")?.textContent).toContain("Existing");
    act(() => FakeSource.instances[0].emit(event("agent.message.delta", 3, {
      message_id: id, text: "reply",
    })));
    expect(screen.queryByText("Existing reply")).toBeNull();
    act(() =>
      FakeSource.instances[0].emit(
        event("agent.message.completed", 4, {
          message_id: id,
          text: "Existing reply",
        }),
      ),
    );
    // Completion and an already-cached final reply cannot skip the reveal queue.
    expect(screen.queryByText("Existing reply")).toBeNull();
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getAllByText("Existing reply")).toHaveLength(1);
    expect(document.querySelector(".rider-investigation")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Checking trips")).toBeTruthy();
  } finally {
    cleanup();
    vi.useRealTimers();
    HTMLElement.prototype.scrollIntoView = original;
  }
});


it("keeps the composer open after dispute/payment SSE and closes only with the thread", async () => {
  const { riderApi } = await import("@/lib/api/rider");
  const { useThread, riderKeys } = await import("@/components/rider/use-rider-support");
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const { wrapper, client } = setup();
  let status: "OPEN" | "RESOLVED" = "OPEN";
  let disputeStatus = "PAYMENT_PENDING";
  const loadConversation = vi.spyOn(riderApi, "getConversation").mockImplementation(async () => ({
    id: conversation, rider_id: "R033", title: "Both trips", status, source_status: status,
    handler: "AI", updated_at: new Date().toISOString(), last_message: "Payment update", scenario: null,
  }));
  const loadMessages = vi.spyOn(riderApi, "getMessages").mockResolvedValue([{
    id: crypto.randomUUID(), conversation_id: conversation, sender: "AI", text: "Payment update", created_at: new Date().toISOString(),
  }]);
  const loadDisputes = vi.spyOn(riderApi, "getDisputes").mockImplementation(async () => [{
    id: "dispute", conversation_id: conversation, type: "PAYOUT", relevant_date: "2026-09-20",
    status: disputeStatus, policy: "VERIFIED", explanation: "Both trips", expected_rupees: 176,
    historical_rupees: 0, verified_difference_rupees: 176, approved_adjustment_rupees: 176,
    items: [], payment: null,
  }]);
  const start = vi.fn();
  function Thread() {
    const query = useThread("R033", conversation);
    if (!query.data) return null;
    return <><p data-testid="dispute-status">{query.data.disputes[0].status}</p>
      <ChatThread riderId="R033" conversation={query.data.conversation} messages={query.data.messages}
        onScenario={vi.fn()} creating={false} onNewConversation={start} /></>;
  }
  try {
    render(<Thread />, { wrapper });
    await waitFor(() => expect(screen.getByRole("textbox")).toBeTruthy());
    const source = FakeSource.instances[0];
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    disputeStatus = "RESOLVED";
    act(() => source.emit({ ...event("dispute.updated", 1, { status: "RESOLVED" }), rider_id: "R033" }));
    await waitFor(() => expect(screen.getByTestId("dispute-status").textContent).toBe("RESOLVED"));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    act(() => source.emit({ ...event("payment.status_changed", 2, { status: "SUCCEEDED" }), rider_id: "R033" }));
    await waitFor(() => expect(loadConversation.mock.calls.length).toBeGreaterThan(2));
    expect(client.getQueryData<{conversation: {status: string}}>(riderKeys.thread("R033", conversation))?.conversation.status).toBe("OPEN");
    status = "RESOLVED";
    act(() => source.emit({ ...event("conversation.updated", 3, { status: "RESOLVED" }), rider_id: "R033" }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    fireEvent.click(screen.getByRole("button", {name: "Start New Conversation"}));
    expect(start).toHaveBeenCalledTimes(1);
  } finally {
    loadConversation.mockRestore(); loadMessages.mockRestore(); loadDisputes.mockRestore();
    HTMLElement.prototype.scrollIntoView = original;
  }
});

it("allows HUMAN-mode messages without requiring an SSE connection and blocks unauthorized sends", () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const { wrapper } = setup();
  const thread = { id: conversation, rider_id: "R033", title: "Support", status: "HUMAN_HANDLING" as const,
    handler: "OPS" as const, updated_at: new Date().toISOString(), last_message: "", scenario: null };
  const view = render(<ChatThread riderId="R033" conversation={thread} messages={[]}
    onScenario={vi.fn()} creating={false} />, {wrapper});
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
  view.rerender(<ChatThread riderId="R033" conversation={thread} messages={[]}
    onScenario={vi.fn()} creating={false} authorized={false} />);
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(true);
});


it("reserves an AI bubble before saved-message refetch without confusing rider messages", () => {
  const mid = crypto.randomUUID();
  let state = reduceStream(emptyStream, event("agent.started", 1));
  state = reduceStream(state, event("message.created", 2, {message_id: mid, sender: "AI"}));
  expect(state.messageId).toBe(mid);
  expect(state.text).toBe("");
  state = reduceStream(state, event("agent.message.delta", 3, {message_id: mid, text: "Hello "}));
  state = reduceStream(state, event("agent.message.delta", 4, {message_id: mid, text: "world"}));
  expect(state.text).toBe("Hello world");
  const rider = reduceStream(emptyStream, event("message.created", 1, {message_id: mid, sender: "RIDER"}));
  expect(rider.messageId).toBeNull();
});


it("keeps one progressively revealed bubble when a saved reply arrives mid-stream", () => {
  vi.useFakeTimers();
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const {wrapper} = setup();
  const mid = crypto.randomUUID();
  const thread = {id: conversation, rider_id: "R003", title: "Support", status: "OPEN" as const,
    handler: "AI" as const, updated_at: new Date().toISOString(), last_message: "", scenario: null};
  const rider = {id: crypto.randomUUID(), conversation_id: conversation, sender: "RIDER" as const,
    text: "Check payment", created_at: new Date().toISOString()};
  const final = {id: mid, conversation_id: conversation, sender: "AI" as const,
    text: "Complete answer", created_at: new Date().toISOString()};
  const props = {riderId: "R003", conversation: thread, onScenario: vi.fn(), creating: false};
  try {
    const view = render(<ChatThread {...props} messages={[rider]} />, {wrapper});
    const source = FakeSource.instances[0];
    act(() => {
      source.emit(event("agent.started", 1));
      source.emit(event("message.created", 2, {message_id: mid, sender: "AI"}));
      source.emit(event("agent.message.delta", 3, {message_id: mid, text: "Complete "}));
    });
    act(() => vi.advanceTimersByTime(64));
    const bubble = document.querySelectorAll(".rider-message-bubble")[1];
    expect(bubble.querySelector("p")?.textContent).toBe("Comp");
    view.rerender(<ChatThread {...props} messages={[rider, final]} />);
    expect(document.querySelectorAll(".rider-message-bubble")[1]).toBe(bubble);
    expect(bubble.querySelector("p")?.textContent).toBe("Comp");
    act(() => {
      source.emit(event("agent.message.delta", 4, {message_id: mid, text: "answer"}));
      source.emit(event("agent.message.completed", 5, {message_id: mid, text: final.text}));
    });
    expect(screen.queryByText(final.text)).toBeNull();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getAllByText(final.text)).toHaveLength(1);
    expect(document.querySelectorAll(".rider-message-bubble")[1]).toBe(bubble);
  } finally {
    cleanup(); vi.useRealTimers(); HTMLElement.prototype.scrollIntoView = original;
  }
});
