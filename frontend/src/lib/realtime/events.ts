import { z } from "zod";
export const eventNames = [
  "agent.started",
  "agent.status",
  "agent.message.delta",
  "agent.message.completed",
  "agent.completed",
  "agent.failed",
  "message.created",
  "conversation.updated",
  "conversation.takeover",
  "conversation.handoff",
  "dispute.updated",
  "ops.case.created",
  "ops.case.updated",
  "payment.status_changed",
  "payment.reconciled",
] as const;
export const eventSchema = z.object({
  event_id: z.uuid(),
  event_type: z.enum(eventNames),
  conversation_id: z.uuid(),
  rider_id: z.string(),
  run_id: z.uuid(),
  sequence: z.number().int().positive(),
  timestamp: z.iso.datetime({ offset: true }),
  data: z.object({
    status: z.string().optional(),
    message_id: z.uuid().optional(),
    text: z.string().optional(),
    sender: z.enum(["AI", "RIDER", "OPS"]).optional(),
    dispute_id: z.uuid().optional(),
    case_id: z.uuid().optional(),
    payment_id: z.uuid().optional(),
    control_version: z.number().int().optional(),
  }),
});
export type LiveEvent = z.infer<typeof eventSchema>;
export function parseEvent(raw: string): LiveEvent | null {
  try {
    return eventSchema.parse(JSON.parse(raw));
  } catch {
    return null;
  }
}
export interface StreamState {
  runId: string | null;
  sequence: number;
  text: string;
  messageId: string | null;
  status: string | null;
  complete: boolean;
  gap: boolean;
  controlVersion: number;
  activity: string[];
}
export const emptyStream: StreamState = {
  runId: null,
  sequence: 0,
  text: "",
  messageId: null,
  status: null,
  complete: false,
  gap: false,
  controlVersion: 0,
  activity: [],
};
export function reduceStream(
  previous: StreamState,
  event: LiveEvent,
): StreamState {
  const version = event.data.control_version ?? previous.controlVersion;
  if (version < previous.controlVersion) return previous;
  const state = { ...previous, controlVersion: version };
  if (event.event_type === "conversation.handoff")
    return { ...emptyStream, controlVersion: state.controlVersion };
  if (
    event.event_type === "conversation.takeover" ||
    event.data.status === "HUMAN_HANDLING"
  )
    return {
      ...emptyStream,
      controlVersion: state.controlVersion,
      status: "human_support",
    };
  // Identify the incoming AI row before a fast query refetch can reveal it in full.
  if (event.event_type === "message.created" && event.data.sender === "AI" &&
      event.data.message_id && (!state.runId || state.runId === event.run_id)) {
    if (state.runId === event.run_id && event.sequence <= state.sequence) return state;
    return {
      ...state, runId: event.run_id, sequence: event.sequence,
      messageId: event.data.message_id,
      text: state.messageId === event.data.message_id ? state.text : "",
      complete: false,
    };
  }
  if (!event.event_type.startsWith("agent."))
    return state.runId === event.run_id && event.sequence > state.sequence
      ? { ...state, sequence: event.sequence }
      : state;
  const same = state.runId === event.run_id;
  if (state.runId && !same && event.event_type !== "agent.started")
    return state;
  if (same && event.sequence <= state.sequence) return state;
  const gap = same && event.sequence > state.sequence + 1;
  const base = same
    ? state
    : {
        ...emptyStream,
        controlVersion: state.controlVersion,
        runId: event.run_id,
      };
  if (event.event_type === "agent.message.completed")
    return {
      ...base,
      sequence: event.sequence,
      text: event.data.text ?? "",
      messageId: event.data.message_id ?? null,
      status: null,
      complete: true,
      gap: false,
    };
  if (event.event_type === "agent.message.delta")
    return {
      ...base,
      sequence: event.sequence,
      text: gap || base.gap ? "" : base.text + (event.data.text ?? ""),
      messageId: event.data.message_id ?? base.messageId,
      gap: gap || base.gap,
    };
  if (
    event.event_type === "agent.completed" ||
    event.event_type === "agent.failed"
  )
    return { ...base, sequence: event.sequence, status: null, complete: true };
  return {
    ...base,
    sequence: event.sequence,
    status: event.data.status ?? null,
    activity: event.data.status && !base.activity.includes(event.data.status)
      ? [...base.activity, event.data.status].slice(-24)
      : base.activity,
    gap: gap || base.gap,
  };
}
