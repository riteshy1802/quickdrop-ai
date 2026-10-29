export interface Rider {
  id: string;
  name: string;
  city: string;
  demo: true;
}
export type Sender = "RIDER" | "AI" | "OPS";
export type ConversationStatus =
  | "OPEN"
  | "RESOLVED"
  | "HUMAN_HANDLING"
  | "ESCALATED"
  | "AWAITING_INFORMATION"
  | "AWAITING_APPROVAL"
  | "PAYMENT_PENDING"
  | "PAYMENT_VERIFICATION_REQUIRED";
export type Scenario =
  "surge" | "incentive" | "large" | "correct" | "human" | "pending";
export type PaymentStatus =
  | "NOT_INITIATED"
  | "AWAITING_APPROVAL"
  | "PROCESSING"
  | "RECONCILIATION_PENDING"
  | "SUCCEEDED"
  | "FAILED"
  | "PENDING"
  | "UNKNOWN"
  | "NEEDS_REVIEW";
export type PolicyStatus =
  | "VERIFIED"
  | "AUTO_ELIGIBLE"
  | "OPS_APPROVAL"
  | "OUTSIDE_WINDOW"
  | "SUPPORT_REVIEW"
  | "AWAITING_INFORMATION";
export interface Conversation {
  id: string;
  rider_id: string;
  title: string;
  status: ConversationStatus;
  // Persisted thread lifecycle, distinct from payment-derived display status.
  source_status?: ConversationStatus;
  handler: "AI" | "OPS";
  assigned_operator?: string | null;
  resolved_by?: "AI" | "OPS";
  updated_at: string;
  last_message: string;
  scenario: Scenario | null;
}
export interface Message {
  id: string;
  conversation_id: string;
  sender: Sender;
  text: string;
  created_at: string;
  delivery?: "DELIVERED";
  pending?: boolean;
  client_message_id?: string | null;
  system_notice?: boolean;
  visibility?: "RIDER" | "INTERNAL";
}
export interface DisputeItem {
  id: string;
  type: "SURGE" | "INCENTIVE" | "PAYOUT";
  trip_id: string | null;
  description: string;
  expected_rupees?: number;
  historical_rupees?: number;
  difference_rupees: number;
}
export interface PaymentIntent {
  id: string;
  dispute_id: string;
  amount_rupees: number;
  status: PaymentStatus;
  updated_at: string;
}
export interface Dispute {
  id: string;
  conversation_id: string;
  type: string;
  relevant_date: string;
  status: string;
  policy: PolicyStatus;
  explanation: string;
  expected_rupees: number | null;
  historical_rupees: number | null;
  verified_difference_rupees: number | null;
  approved_adjustment_rupees: number | null;
  items: DisputeItem[];
  payment: PaymentIntent | null;
}

// Assignment-required POST /messages body and response. Do not add UI fields.
export interface PostMessageRequest {
  message_id: string;
  rider_id: string;
  text: string;
  received_at: string;
}
export interface PostMessageResponse {
  reply: string;
}
