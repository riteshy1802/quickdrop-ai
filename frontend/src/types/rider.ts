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
  | "AWAITING_APPROVAL"
  | "PAYMENT_PENDING";
export type Scenario =
  | "surge"
  | "incentive"
  | "large"
  | "correct"
  | "human"
  | "pending";
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
  | "AUTO_ELIGIBLE"
  | "OPS_APPROVAL"
  | "OUTSIDE_WINDOW"
  | "AWAITING_INFORMATION";
export interface Conversation {
  id: string;
  rider_id: string;
  title: string;
  status: ConversationStatus;
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
  system_notice?: boolean;
  visibility?: "RIDER" | "INTERNAL";
}
export interface DisputeItem {
  id: string;
  type: "SURGE" | "INCENTIVE" | "PAYOUT";
  trip_id: string | null;
  description: string;
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
  expected_rupees: number;
  historical_rupees: number;
  verified_difference_rupees: number;
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

// Proposed internal UI contracts, not implemented backend endpoints.
export interface RiderUiContracts {
  "GET /ui/riders": { response: Rider[] };
  "GET /ui/riders/{rider_id}/conversations": { response: Conversation[] };
  "GET /ui/conversations/{conversation_id}": { response: Conversation };
  "GET /ui/conversations/{conversation_id}/messages": { response: Message[] };
  "GET /ui/conversations/{conversation_id}/disputes": { response: Dispute[] };
  "GET /ui/conversations/{conversation_id}/events": {
    response: ConversationEvent;
  };
}
export type ProcessingStep =
  | "Message received"
  | "Checking trip records"
  | "Verifying payout details"
  | "Reviewing payment eligibility"
  | "Preparing response";
export type ConversationEvent =
  | { type: "processing"; conversation_id: string; step: ProcessingStep }
  | { type: "message"; conversation_id: string; message: Message }
  | {
      type: "conversation.updated";
      conversation_id: string;
      status: ConversationStatus;
    };
