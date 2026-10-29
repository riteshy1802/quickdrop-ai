import type {
  ConversationStatus,
  PaymentStatus,
  PolicyStatus,
} from "@/types/rider";
export const money = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? "Not available"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0,
      }).format(value);
export const time = (value: string) =>
  new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
export const date = (value: string) =>
  new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
export const statusLabels: Record<ConversationStatus, string> = {
  OPEN: "In conversation",
  RESOLVED: "Resolved",
  HUMAN_HANDLING: "Human handling",
  ESCALATED: "Awaiting support review",
  AWAITING_INFORMATION: "Awaiting details",
  AWAITING_APPROVAL: "Awaiting approval",
  PAYMENT_PENDING: "Payment pending",
  PAYMENT_VERIFICATION_REQUIRED: "Payment verification required",
};
export const paymentLabels: Record<PaymentStatus, string> = {
  PENDING: "Pending",
  UNKNOWN: "Outcome uncertain",
  NEEDS_REVIEW: "Payment verification required",
  NOT_INITIATED: "Not initiated",
  AWAITING_APPROVAL: "Awaiting approval",
  PROCESSING: "Processing",
  RECONCILIATION_PENDING: "Reconciliation pending",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed · Needs review",
};
export const policyLabels: Record<PolicyStatus, string> = {
  VERIFIED: "Verified against source records",
  AUTO_ELIGIBLE: "Eligible for automatic payment",
  OPS_APPROVAL: "Requires Ops approval",
  SUPPORT_REVIEW: "Requires support review",
  OUTSIDE_WINDOW: "Outside dispute eligibility window",
  AWAITING_INFORMATION: "Awaiting additional information",
};
export function relativeActivity(value: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}
