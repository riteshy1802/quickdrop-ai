"use client";

import { useEffect, useMemo, useState } from "react";
import { useReducedMotion } from "motion/react";
import type { Message } from "@/types/rider";
import { ChatMessage } from "./chat-message";

/** Reveal the buffered SSE text even when all deltas arrive in one browser batch. */
export function StreamedMessage({
  message,
  animate,
  onProgress,
}: {
  message: Message;
  animate: boolean;
  onProgress?: () => void;
}) {
  const reducedMotion = useReducedMotion();
  const [revealed, setRevealed] = useState("");
  const graphemes = useMemo(
    () => Array.from(
      new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(message.text),
      (part) => part.segment,
    ),
    [message.text],
  );
  useEffect(() => {
    if (!animate || reducedMotion) return;
    // A corrected authoritative reply replaces stale text; it is never appended to it.
    const step = Math.max(1, Math.ceil(graphemes.length / 90));
    const timer = window.setInterval(() => {
      setRevealed((previous) => {
        const prefix = message.text.startsWith(previous) ? previous : "";
        const count = Array.from(
          new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(prefix),
        ).length;
        const next = graphemes.slice(0, count + step).join("");
        if (next === message.text) window.clearInterval(timer);
        return next;
      });
    }, 16);
    return () => window.clearInterval(timer);
  }, [animate, reducedMotion, message.text, graphemes]);
  const text = !animate || reducedMotion
    ? message.text
    : message.text.startsWith(revealed) ? revealed : "";
  useEffect(() => {
    onProgress?.();
  }, [text, onProgress]);
  return <ChatMessage message={{ ...message, text }} />;
}
