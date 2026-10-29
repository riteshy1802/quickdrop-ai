import type {
  Conversation,
  Dispute,
  Message,
  PaymentIntent,
  Rider,
} from "./rider";
export interface OpsUser {
  id: string;
  name: string;
  email: string;
  role: "Demo operator" | "Administrator";
}
export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { [key: string]: Json };
export interface WorkspaceThread {
  conversation: Conversation;
  messages: Message[];
  disputes: Dispute[];
}
export type CaseStatus =
  | "PENDING"
  | "IN_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "RESOLVED";
export interface PolicyCheck {
  label: string;
  result: "PASSED" | "FAILED" | "REVIEW" | "UNKNOWN";
}
export interface OpsQueueItem {
  id: string;
  conversation_id: string;
  dispute_id: string;
  rider_id: string;
  kind: "APPROVAL" | "ESCALATION";
  status: CaseStatus;
  amount_rupees: number | null;
  claimed_rupees: number | null;
  reason: string;
  category: string;
  created_at: string;
  assigned_to: string | null;
  reviewed_at: string | null;
  rejection_reason?: string;
  checks: PolicyCheck[];
}
export interface ProviderAttempt {
  number: number;
  created_at: string;
  http_status: number | null;
  duration_ms: number | null;
  result: string;
  retry_scheduled: boolean;
  error_category: string | null;
}
export interface OpsPayout extends PaymentIntent {
  rider_id: string;
  conversation_id: string;
  initiation: "AUTO" | "HUMAN_APPROVED";
  created_at: string;
  provider_id: string | null;
  provider_status: string;
  reconciled_at: string | null;
  reconciliation_outcome: string;
  attempts: ProviderAttempt[];
  lifecycle: { name: string; at: string }[];
}
export type TraceType =
  | "message_in"
  | "tool_call"
  | "decision"
  | "reply"
  | "error"
  | "operator_action"
  | "approval_decision"
  | "payment_execution"
  | "reconciliation";
export interface AgentTrace {
  id: string;
  created_at: string;
  type: TraceType;
  rider_id: string;
  conversation_id: string;
  dispute_id?: string;
  payment_id?: string;
  name: string;
  status: "OK" | "PENDING" | "ERROR";
  correlation_id: string;
  input: Json;
  output: Json;
  duration_ms: number | null;
}
export interface OpsNotification {
  id: string;
  title: string;
  detail: string;
  href: string;
  created_at: string;
  read: boolean;
}
export interface OpsSnapshot {
  riders: Rider[];
  threads: WorkspaceThread[];
  cases: OpsQueueItem[];
  payouts: OpsPayout[];
  traces: AgentTrace[];
  notifications: OpsNotification[];
}
export type OpsAction =
  | { type: "takeover" | "handoff" | "resolve_conversation"; id: string; reason?: string }
  | { type: "reply" | "note"; id: string; text: string; client_request_id?: string }
  | {
      type: "approve" | "reject" | "assign" | "resolve_case";
      id: string;
      reason?: string;
    }
  | { type: "reconcile"; id: string }
  | { type: "read_notification"; id: string };
export interface LoginInput {
  email: string;
  password: string;
}
