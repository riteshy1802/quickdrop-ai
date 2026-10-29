import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { request, post, allPages, ApiError } from "@/lib/api/client";
import { opsAuth } from "@/lib/api/auth";
import { mapPayout, mapDispute, type PayoutRecord } from "@/lib/api/contracts";
import {
  useConversations,
  useSendMessage,
  riderKeys,
  useRiderContext,
} from "@/components/rider/use-rider-support";
import { OpsAuthProvider, useOpsAuth } from "@/components/ops/auth-context";
import { statusLabels, policyLabels, paymentLabels } from "@/components/rider/format";
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
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
it("uses credentialed JSON requests and server error messages", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ id: "a" }))
    .mockResolvedValueOnce(
      json({ error: { message: "Approval still pending" } }, 409),
    );
  vi.stubGlobal("fetch", fetch);
  expect(await post("/action", { reason: "Reviewed" })).toEqual({ id: "a" });
  expect(fetch.mock.calls[0][1]).toMatchObject({
    credentials: "include",
    method: "POST",
    body: '{"reason":"Reviewed"}',
  });
  await expect(request("/action")).rejects.toThrow("Approval still pending");
});
it("does not silently return mocks when the backend is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  await expect(request("/ui/riders")).rejects.toBeInstanceOf(ApiError);
});
it("loads every page using server totals", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ items: [1, 2], total: 3 }))
    .mockResolvedValueOnce(json({ items: [3], total: 3 }));
  vi.stubGlobal("fetch", fetch);
  expect(await allPages("/items")).toEqual([1, 2, 3]);
  expect(fetch.mock.calls[1][0]).toContain("offset=2");
});
it("does not present approved or pending payments as succeeded", () => {
  const p: PayoutRecord = {
    id: "id",
    dispute_id: "d",
    rider_id: "R003",
    conversation_id: "c",
    amount_rupees: "425",
    status: "PENDING",
    initiation: "HUMAN_APPROVED",
    provider_id: null,
    reconciled_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    retry_count: 0,
    next_retry_at: null,
  };
  expect(mapPayout(p).status).toBe("PENDING");
  expect(mapPayout(p).provider_status).not.toBe("processed");
  const d = mapDispute(
    {
      id: "d",
      conversation_id: "c",
      status: "PAYMENT_PENDING",
      verified_amount: "425",
      created_at: p.created_at,
      items: [],
    },
    [p],
  );
  expect(d.payment?.status).toBe("PENDING");
  expect(
    mapPayout({ ...p, status: "SUCCEEDED", provider_id: "provider-confirmed" })
      .provider_status,
  ).toBe("processed");
});
it("shows escalation as support review without inventing a payment", () => {
  const d = mapDispute({
    id: "d", conversation_id: "c", status: "ESCALATED",
    verified_amount: null, created_at: new Date().toISOString(), items: [],
  });
  expect(statusLabels.ESCALATED).toBe("Awaiting support review");
  expect(policyLabels[d.policy]).toBe("Requires support review");
  expect(d.payment).toBeNull();
  expect(d.approved_adjustment_rupees).toBeNull();
  expect(d.verified_difference_rupees).toBeNull();
});
it("labels review-held payments as requiring verification", () => {
  expect(paymentLabels.NEEDS_REVIEW).toBe("Payment verification required");
  expect(statusLabels.PAYMENT_VERIFICATION_REQUIRED).toBe("Payment verification required");
});
it("selects a signed demo context before querying rider conversations", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ rider_id: "R003" }))
    .mockResolvedValueOnce(json({ items: [], total: 0 }));
  vi.stubGlobal("fetch", fetch);
  const { wrapper } = setup();
  const hook = renderHook(
    () => {
      const context = useRiderContext("R003");
      return useConversations("R003", context.isSuccess);
    },
    { wrapper },
  );
  await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
  expect(fetch.mock.calls[0][0]).toContain("/ui/demo/rider");
  expect(fetch.mock.calls[1][0]).toContain("/ui/riders/R003/conversations");
});
it("sends the same webhook ID on explicit retries and invalidates saved history", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ error: { message: "Retry same ID" } }, 503))
    .mockResolvedValueOnce(json({ reply: "Saved" }));
  vi.stubGlobal("fetch", fetch);
  const { wrapper, client } = setup();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const hook = renderHook(() => useSendMessage("R003", "conversation"), {
    wrapper,
  });
  const payload = {
    message_id: "stable-id",
    rider_id: "R003",
    text: "Payout issue",
    received_at: new Date().toISOString(),
  };
  await act(async () => {
    await expect(
      hook.result.current.mutateAsync({ request: payload }),
    ).rejects.toThrow("Retry same ID");
  });
  await act(async () => {
    await hook.result.current.mutateAsync({ request: payload });
  });
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({
    conversation_id: "conversation",
    message_id: "stable-id",
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: riderKeys.thread("R003", "conversation"),
  });
});
it("uses backend session identity and clears protected state on expiration", async () => {
  class Source extends EventTarget {
    close() {}
  }
  vi.stubGlobal("EventSource", Source);
  const user = { id: "real-admin", email: "admin@example.com" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(user)));
  const { client } = setup();
  client.setQueryData(["ops-data"], { private: "records" });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <OpsAuthProvider>{children}</OpsAuthProvider>
    </QueryClientProvider>
  );
  const hook = renderHook(() => useOpsAuth(), { wrapper });
  await waitFor(() => expect(hook.result.current.user?.id).toBe("real-admin"));
  act(() => window.dispatchEvent(new Event("quickdrop:session-expired")));
  await waitFor(() => expect(hook.result.current.user).toBeNull());
  expect(client.getQueryData(["ops-data"])).toBeUndefined();
});
it("maps an unauthorized session to signed-out state", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(json({ error: { message: "Session expired" } }, 401)),
  );
  expect(await opsAuth.me()).toBeNull();
});

it("keeps missing verification distinct from a verified zero", () => {
  const d = mapDispute({
    id: "d",
    conversation_id: "c",
    status: "INVESTIGATING",
    verified_amount: null,
    created_at: new Date().toISOString(),
    items: [],
  });
  expect(d.verified_difference_rupees).toBeNull();
  expect(d.expected_rupees).toBeNull();
});

it("sends approvals only to the Ops API without selecting a payment amount", async () => {
  const { opsApi } = await import("@/lib/api/ops");
  const fetch = vi
    .fn()
    .mockResolvedValue(json({ status: "APPROVED", payment_confirmed: false }));
  vi.stubGlobal("fetch", fetch);
  await opsApi.act(
    { type: "approve", id: "case-id" },
    {
      id: "admin",
      name: "Admin",
      email: "admin@test.invalid",
      role: "Administrator",
    },
  );
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/backend/ui/ops/cases/case-id/approve",
  );
  expect(fetch.mock.calls[0][1].body).toBeUndefined();
});

it("retains human message idempotency identifiers through the live adapter", async () => {
  const { opsApi } = await import("@/lib/api/ops");
  const fetch = vi
    .fn()
    .mockImplementation(async () => json({ id: "message-id" }));
  vi.stubGlobal("fetch", fetch);
  const action = {
    type: "reply" as const,
    id: "conversation",
    text: "Support reply",
    client_request_id: crypto.randomUUID(),
  };
  const operator = {
    id: "admin",
    name: "Admin",
    email: "admin@test.invalid",
    role: "Administrator" as const,
  };
  await opsApi.act(action, operator);
  await opsApi.act(action, operator);
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
});

it("maps recorded provider attempts without marking success as an error", async () => {
  const { opsApi } = await import("@/lib/api/ops");
  const at = new Date().toISOString();
  const payout = {
    id: "payment",
    dispute_id: "d",
    conversation_id: "c",
    rider_id: "R003",
    amount_rupees: "425",
    status: "SUCCEEDED",
    initiation: "HUMAN_APPROVED",
    provider_id: "confirmed",
    reconciled_at: at,
    created_at: at,
    updated_at: at,
    retry_count: 2,
    next_retry_at: null,
  };
  const trace = {
    id: "trace",
    at,
    type: "tool_call",
    rider_id: "R003",
    conversation_id: "c",
    name: "payswift_request_result",
    input: { intent_id: "payment", attempt: 2 },
    output: {
      status: "SUCCEEDED",
      outcome: "provider_confirmed",
      http_status: 201,
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input: string) => {
      const items = input.includes("/ui/ops/payouts")
        ? [payout]
        : input.includes("/ui/ops/traces")
          ? [trace]
          : [];
      return json({ items, total: items.length, limit: 100, offset: 0 });
    }),
  );
  const snapshot = await opsApi.getSnapshot();
  expect(snapshot.payouts[0].attempts[0]).toMatchObject({
    number: 2,
    error_category: null,
    http_status: 201,
    result: "SUCCEEDED",
  });
  expect(snapshot.payouts[0].lifecycle).toHaveLength(2);
});
