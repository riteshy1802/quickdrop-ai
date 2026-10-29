import type {
  Conversation,
  Message,
  Dispute,
  PaymentStatus,
} from "@/types/rider";
import type { OpsPayout } from "@/types/ops";
export interface RiderRecord {
  rider_id: string;
  name: string;
  city: string;
}
export interface ConversationRecord extends Conversation {
  assigned_operator_id: string | null;
  control_version: number;
}
export interface MessageRecord extends Message {
  operator_id: string | null;
}
export interface ItemRecord {
  id: string;
  source_type: string;
  source_id: string;
  expected_amount: string;
  actual_amount: string;
  difference: string;
}
export interface DisputeRecord {
  id: string;
  conversation_id: string;
  status: string;
  verified_amount: string | null;
  created_at: string;
  items: ItemRecord[];
}
export interface PayoutRecord {
  id: string;
  dispute_id: string;
  rider_id: string;
  conversation_id: string;
  amount_rupees: string;
  status: PaymentStatus;
  initiation: "AUTO" | "HUMAN_APPROVED";
  provider_id: string | null;
  reconciled_at: string | null;
  created_at: string;
  updated_at: string;
  retry_count: number;
  next_retry_at: string | null;
}
export function mapConversation(row: ConversationRecord): Conversation {
  return { ...row, assigned_operator: row.assigned_operator_id };
}
export function mapPayout(p: PayoutRecord): OpsPayout {
  return {
    ...p,
    amount_rupees: Number(p.amount_rupees),
    provider_status:
      p.status === "SUCCEEDED" && p.provider_id ? "processed" : p.status,
    reconciliation_outcome: p.reconciled_at
      ? `Last reconciled ${p.reconciled_at}`
      : "Not reconciled",
    attempts: [],
    lifecycle: [{ name: "Intent created", at: p.created_at }],
  };
}
export function mapDispute(
  d: DisputeRecord,
  payouts: PayoutRecord[] = [],
): Dispute {
  const payment = payouts.find((p) => p.dispute_id === d.id);
  const expected = d.items.reduce(
    (sum, i) => sum + Number(i.expected_amount),
    0,
  );
  const historical = d.items.reduce(
    (sum, i) => sum + Number(i.actual_amount),
    0,
  );
  return {
    id: d.id,
    conversation_id: d.conversation_id,
    type: "Payout reconciliation",
    relevant_date: d.created_at,
    status: d.status,
    policy:
      d.status === "AWAITING_APPROVAL"
        ? "OPS_APPROVAL"
        : d.status === "ESCALATED"
          ? "SUPPORT_REVIEW"
          : d.verified_amount !== null
            ? "VERIFIED"
            : "AWAITING_INFORMATION",
    explanation:
      d.verified_amount === null
        ? "Investigation is awaiting verified evidence."
        : "Verified source records and current payment state.",
    expected_rupees: d.items.length ? expected : null,
    historical_rupees: d.items.length ? historical : null,
    verified_difference_rupees:
      d.verified_amount === null ? null : Number(d.verified_amount),
    approved_adjustment_rupees: payment ? Number(payment.amount_rupees) : null,
    items: d.items.map((i) => ({
      id: i.id,
      type: "PAYOUT",
      trip_id: i.source_type === "trip" ? i.source_id : null,
      description: `${i.source_type}: ${i.source_id}`,
      expected_rupees: Number(i.expected_amount),
      historical_rupees: Number(i.actual_amount),
      difference_rupees: Number(i.difference),
    })),
    payment: payment ? mapPayout(payment) : null,
  };
}
