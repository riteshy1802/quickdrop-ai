import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CaseReview } from "@/components/ops/approvals";
import type { OpsSnapshot, PolicyCheck } from "@/types/ops";
vi.mock("@/components/ops/use-ops", () => ({ useOpsAction: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }) }));
vi.mock("@/components/ops/common", () => ({
  OpsData: () => null, PageHeading: ({children}: {children: React.ReactNode}) => <div>{children}</div>,
  Panel: ({children}: {children: React.ReactNode}) => <div>{children}</div>, Segments: () => null,
  StatusBadge: () => null, EmptyState: () => null, Feedback: () => null,
  money: (v: number) => String(v), date: (v: string) => v,
}));
afterEach(cleanup);
function data(kind = "APPROVAL", checks: PolicyCheck[] = [], status = "PENDING") {
  return {riders: [], cases: [{id: "case", kind, status, checks, conversation_id: "thread", dispute_id: "dispute", rider_id: "R016", reason: "Review", amount_rupees: 425}], threads: [{conversation: {id: "thread"}, messages: [], disputes: [{id: "dispute", items: [], related_trip_ids: []}]}]} as unknown as OpsSnapshot;
}
it("hides unsupported assignment for approval, retains escalation assignment", () => {
  const view = render(<CaseReview id="case" data={data()} />);
  expect(screen.queryByText("Assign to me")).toBeNull();
  view.rerender(<CaseReview id="case" data={data("ESCALATION")} />);
  expect(screen.getByText("Assign to me")).toBeTruthy();
});
it.each([[], undefined])("shows unavailable evidence without claiming success", (checks) => {
  render(<CaseReview id="case" data={data("APPROVAL", checks)} />);
  expect(screen.getByText("Evidence checks unavailable")).toBeTruthy();
  expect((screen.getByText("Approve payment") as HTMLButtonElement).disabled).toBe(false);
});
it.each(["PASSED", "FAILED", "UNKNOWN"] as const)("renders %s evidence and blocks explicit failures", (result) => {
  render(<CaseReview id="case" data={data("APPROVAL", [{label: "Ownership", result}])} />);
  expect(screen.getByText("Ownership")).toBeTruthy();
  expect((screen.getByText("Approve payment") as HTMLButtonElement).disabled).toBe(result === "FAILED");
});
it("keeps closed approvals closed", () => {
  render(<CaseReview id="case" data={data("APPROVAL", [], "APPROVED")} />);
  expect(screen.queryByText("Approve payment")).toBeNull();
});
