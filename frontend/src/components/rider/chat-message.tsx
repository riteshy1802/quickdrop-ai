"use client";
import { motion } from "motion/react";
import { CheckCheck, Sparkles, UserRoundCheck } from "lucide-react";
import type { Message } from "@/types/rider";
import { time } from "./format";
export function ChatMessage({ message }: { message: Message }) {
  if (message.system_notice)
    return (
      <div className="rider-system-notice">
        <UserRoundCheck size={14} />
        {message.text}
      </div>
    );
  const rider = message.sender === "RIDER",
    ops = message.sender === "OPS";
  return (
    <motion.div
      className={`rider-message-row ${rider ? "from-rider" : "from-support"} ${ops ? "from-ops" : ""}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      {!rider && (
        <span className="rider-message-avatar">
          {ops ? <UserRoundCheck size={15} /> : <Sparkles size={15} />}
        </span>
      )}
      <div className="rider-message-content">
        <div className="rider-message-sender">
          {rider ? "You" : ops ? "Human Support" : "QuickDrop AI"}
          {!rider && <span>{ops ? "SUPPORT TEAM" : "AI ASSISTANT"}</span>}
        </div>
        <div className="rider-message-bubble">
          <p>{message.text}</p>
          <div className="rider-message-time">
            <time dateTime={message.created_at}>
              {time(message.created_at)}
            </time>
            {message.delivery && (
              <CheckCheck size={13} aria-label="Delivered" />
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
