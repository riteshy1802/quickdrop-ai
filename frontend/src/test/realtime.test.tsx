import { ChatThread } from "@/components/rider/chat-thread";
import { act, cleanup, render, screen, renderHook, waitFor } from "@testing-library/react";
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
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false })),
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
    expect(document.querySelector(".rider-message-bubble")?.textContent).toContain("Existing");
    act(() => FakeSource.instances[0].emit(event("agent.message.delta", 3, {
      message_id: id, text: "reply",
    })));
    expect(screen.getAllByText("Existing reply")).toHaveLength(1);
    act(() =>
      FakeSource.instances[0].emit(
        event("agent.message.completed", 4, {
          message_id: id,
          text: "Existing reply",
        }),
      ),
    );
    expect(screen.getAllByText("Existing reply")).toHaveLength(1);
    expect(document.querySelector(".rider-investigation")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("Checking trips")).toBeTruthy();
  } finally {
    HTMLElement.prototype.scrollIntoView = original;
  }
});
