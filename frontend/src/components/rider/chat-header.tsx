import { ArrowLeft, PanelRight, Sparkles, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { statusLabels } from "./format";
import type { Conversation } from "@/types/rider";
export function ChatHeader({
  conversation,
  onSidebar,
  onDetails,
  detailsOpen,
}: {
  conversation?: Conversation;
  onSidebar: () => void;
  onDetails: () => void;
  detailsOpen: boolean;
}) {
  const human = conversation?.handler === "OPS";
  return (
    <header className="rider-chat-header">
      <Button
        size="icon"
        variant="ghost"
        className="rider-mobile-back"
        aria-label="Open conversations"
        onClick={onSidebar}
      >
        <ArrowLeft size={19} />
      </Button>
      <div className={`rider-support-avatar ${human ? "human" : ""}`}>
        {human ? <UserRoundCheck size={21} /> : <Sparkles size={21} />}
      </div>
      <div className="rider-header-title">
        <h1>QuickDrop AI Support</h1>
        <span>
          <i />
          {human ? "Human Support is handling this" : "Your payout, explained"}
        </span>
      </div>
      <div className="rider-header-status">
        {conversation && (
          <Badge
            variant="outline"
            className={`rider-status-badge ${conversation.status.toLowerCase()}`}
          >
            {statusLabels[conversation.status]}
          </Badge>
        )}
      </div>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Toggle dispute details"
        aria-expanded={detailsOpen}
        onClick={onDetails}
      >
        <PanelRight size={19} />
      </Button>
    </header>
  );
}
