"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { ArrowDown, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  Conversation,
  Message,
  PostMessageRequest,
  Scenario,
} from "@/types/rider";
import { ChatMessage } from "./chat-message";
import { InvestigationActivity } from "./investigation-activity";
import { MessageComposer } from "./message-composer";
import { ConversationEmptyState } from "./conversation-empty-state";
import { date } from "./format";
import { useConversationEvents } from "@/hooks/realtime/use-events";
import { useSendMessage } from "./use-rider-support";
const statuses: Record<string, string> = {
  verification_pending: "Verification is pending; saved work will resume",
  started: "Starting investigation",
  understanding_complaint: "Understanding complaint",
  checking_trip_records: "Checking trip records",
  retrieving_payout_history: "Retrieving payout history",
  calculating_verified_shortfall: "Calculating verified shortfall",
  checking_payment_eligibility: "Checking payment eligibility",
  authorizing_payment: "Checking payment authorization",
  retry_pending: "Verification will retry",
  investigation_failed: "Investigation unavailable; awaiting support review",
  escalating_to_ops: "Escalating to Ops",
  preparing_response: "Preparing response",
  human_support: "Human Support is handling this conversation",
};
export function ChatThread({
  riderId,
  conversation,
  messages,
  onScenario,
  creating,
}: {
  riderId: string;
  conversation: Conversation;
  messages: Message[];
  onScenario: (scenario: Scenario) => void;
  creating: boolean;
}) {
  const mutation = useSendMessage(riderId, conversation.id);
  const retryRequest = useRef<PostMessageRequest | null>(null);
  const live = useConversationEvents(conversation.id, riderId);
  const log = useRef<HTMLDivElement>(null);
  const latest = useRef<HTMLDivElement>(null);
  const [away, setAway] = useState(false);
  const shouldScroll = useRef(true);
  useEffect(() => {
    if (shouldScroll.current)
      latest.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "end",
      });
  }, [messages.length, mutation.isPending, live.stream.text, live.stream.activity.length]);
  async function send(text: string) {
    const previous = retryRequest.current;
    const request: PostMessageRequest =
      previous?.text === text
        ? previous
        : {
            message_id: `wamid.demo.${crypto.randomUUID()}`,
            rider_id: riderId,
            text,
            received_at: new Date().toISOString(),
          };
    retryRequest.current = request;
    shouldScroll.current = true;
    try {
      await mutation.mutateAsync({ request });
      retryRequest.current = null;
      return true;
    } catch {
      return false;
    }
  }
  const pendingRequest = mutation.variables?.request;
  const pendingMessage: Message | undefined =
    mutation.isPending &&
    pendingRequest &&
    !messages.some((m) => m.client_message_id === pendingRequest.message_id)
      ? {
          id: pendingRequest.message_id,
          pending: true,
          conversation_id: conversation.id,
          sender: "RIDER",
          text: pendingRequest.text,
          created_at: pendingRequest.received_at,
        }
      : undefined;
  return (
    <>
      <div
        ref={log}
        className="rider-message-scroll"
        onScroll={() => {
          const node = log.current;
          if (node) {
            const near =
              node.scrollHeight - node.scrollTop - node.clientHeight < 90;
            shouldScroll.current = near;
            setAway(!near);
          }
        }}
      >
        {messages.length === 0 && !mutation.isPending ? (
          <ConversationEmptyState onScenario={onScenario} creating={creating} />
        ) : (
          <div
            className="rider-message-log"
            role="log"
            aria-label="Conversation messages"
            aria-live="polite"
            aria-relevant="additions"
          >
            {messages.map((message, index) => {
              const group = date(message.created_at),
                previous =
                  index > 0 ? date(messages[index - 1].created_at) : null;
              return (
                <Fragment key={message.id}>
                  {group !== previous && (
                    <div className="rider-date-divider">
                      <span />
                      {group}
                      <span />
                    </div>
                  )}
                  {message.id === live.stream.messageId && conversation.handler !== "OPS" && (
                    <InvestigationActivity activity={live.stream.activity} complete={live.stream.complete} />
                  )}
                  {(message.id !== live.stream.messageId || live.stream.complete) && (
                    <ChatMessage message={message} />
                  )}
                </Fragment>
              );
            })}
            {pendingMessage && <ChatMessage message={pendingMessage} />}
            {conversation.handler !== "OPS" && !messages.some((m) => m.id === live.stream.messageId) && (
              <InvestigationActivity activity={live.stream.activity} complete={live.stream.complete} />
            )}
            {conversation.handler !== "OPS" &&
              live.stream.text &&
              live.stream.messageId &&
              (!live.stream.complete || !messages.some((m) => m.id === live.stream.messageId)) && (
                <ChatMessage
                  message={{
                    id: live.stream.messageId,
                    conversation_id: conversation.id,
                    sender: "AI",
                    text: live.stream.text,
                    created_at: new Date().toISOString(),
                  }}
                />
              )}
            {(live.stream.status ||
              mutation.isPending ||
              live.connection === "reconnecting") && (
              <div role="status" className="rider-processing">
                <Sparkles size={15} />
                <span>
                  {live.connection === "reconnecting"
                    ? "Reconnecting · saved messages will refresh"
                    : conversation.handler === "OPS"
                      ? "Human Support is handling this conversation"
                      : (statuses[live.stream.status ?? ""] ??
                        (mutation.isPending
                          ? "Sending message…"
                          : "Waiting for investigation"))}
                </span>
              </div>
            )}
            <div ref={latest} />
          </div>
        )}
      </div>
      {away && (
        <Button
          size="sm"
          variant="secondary"
          className="rider-scroll-latest"
          onClick={() => {
            shouldScroll.current = true;
            latest.current?.scrollIntoView({
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                .matches
                ? "instant"
                : "smooth",
            });
          }}
        >
          <ArrowDown size={13} />
          Latest messages
        </Button>
      )}
      <MessageComposer
        pending={mutation.isPending || live.connection === "connecting"}
        error={mutation.error?.message ?? null}
        onSend={send}
      />
    </>
  );
}
