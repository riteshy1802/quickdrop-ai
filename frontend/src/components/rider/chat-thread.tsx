"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { ArrowDown, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  Conversation,
  Message,
  PostMessageRequest,
  ProcessingStep,
  Scenario,
} from "@/types/rider";
import { ChatMessage } from "./chat-message";
import { MessageComposer } from "./message-composer";
import { ConversationEmptyState } from "./conversation-empty-state";
import { date } from "./format";
import { useSendMessage } from "./use-rider-support";
const stages: ProcessingStep[] = [
  "Message received",
  "Checking trip records",
  "Verifying payout details",
  "Reviewing payment eligibility",
  "Preparing response",
];
function ProcessingIndicator({ human }: { human: boolean }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setStep((current) => Math.min(current + 1, stages.length - 1)),
      220,
    );
    return () => clearInterval(timer);
  }, []);
  return (
    <div role="status" className="rider-processing">
      <Sparkles size={15} />
      <span>
        {human ? "Preparing a sample Human Support reply" : stages[step]}
        <small>Simulated demo step · No live tools are running</small>
      </span>
      <i />
      <i />
      <i />
    </div>
  );
}
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
  const failureArmed = useRef(false);
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
  }, [messages.length, mutation.isPending]);
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
      const simulateFailure = failureArmed.current;
      failureArmed.current = false;
      await mutation.mutateAsync({ request, simulateFailure });
      retryRequest.current = null;
      return true;
    } catch {
      return false;
    }
  }
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
                  <ChatMessage message={message} />
                </Fragment>
              );
            })}
            {mutation.isPending && (
              <ProcessingIndicator human={conversation.handler === "OPS"} />
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
        pending={mutation.isPending}
        error={mutation.error?.message ?? null}
        onSend={send}
        onSimulateError={() => {
          failureArmed.current = true;
        }}
      />
    </>
  );
}
