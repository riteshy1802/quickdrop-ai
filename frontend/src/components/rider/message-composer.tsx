"use client";
import { useRef, useState } from "react";
import { ArrowUp, RotateCcw, ShieldCheck, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
export function MessageComposer({
  onSend,
  pending,
  error,
}: {
  onSend: (text: string) => Promise<boolean>;
  pending: boolean;
  error: string | null;
}) {
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  async function submit() {
    if (!text.trim() || pending) return;
    if (await onSend(text.trim())) {
      setText("");
      input.current?.focus();
    }
  }
  return (
    <div className="rider-composer-wrap">
      {error && (
        <div role="alert" className="rider-send-error">
          <WifiOff size={15} />
          <span>{error}</span>
          <Button variant="ghost" size="sm" disabled={pending} onClick={submit}>
            <RotateCcw size={13} />
            Retry
          </Button>
        </div>
      )}
      <form
        className="rider-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="rider-message-input" className="sr-only">
          Your message
        </label>
        <Textarea
          ref={input}
          id="rider-message-input"
          value={text}
          disabled={pending}
          maxLength={4000}
          rows={2}
          placeholder="Describe your payout issue…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="rider-composer-controls">
          <span>English · हिन्दी · Hinglish</span>
          <span className="rider-keyboard-hint">
            Shift + Enter for a new line
          </span>
          <Button
            type="submit"
            size="icon"
            className="rider-send-button"
            disabled={pending || !text.trim()}
            aria-label={error ? "Retry sending message" : "Send message"}
          >
            <ArrowUp size={18} />
          </Button>
        </div>
      </form>
      <div className="rider-composer-note">
        <span>
          <ShieldCheck size={11} />
          Demo only. No real money moves.
        </span>

      </div>
    </div>
  );
}
