"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpLeft,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Logo } from "@/components/shared/logo";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { RiderSelector } from "./rider-selector";
import { relativeActivity, statusLabels } from "./format";
import type { Conversation, Rider } from "@/types/rider";
export function ConversationSidebar({
  rider,
  riders,
  onRider,
  conversations,
  activeId,
  onSelect,
  onNew,
  loading,
  creating,
}: {
  rider: Rider;
  riders: Rider[];
  onRider: (id: string) => void;
  conversations: Conversation[];
  activeId?: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  loading: boolean;
  creating: boolean;
}) {
  const [search, setSearch] = useState("");
  const filtered = conversations.filter((c) =>
    (c.title + " " + c.last_message)
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="rider-sidebar-inner">
      <div className="rider-sidebar-brand">
        <Logo />
        <span>RIDER SUPPORT</span>
      </div>
      <RiderSelector riders={riders} rider={rider} onChange={onRider} />
      <Button className="rider-new-button" onClick={onNew} disabled={creating}>
        <Plus size={16} />
        {creating ? "Starting…" : "New conversation"}
      </Button>
      <label className="rider-search">
        <Search size={14} />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search conversations"
          aria-label="Search conversations"
        />
      </label>
      <div className="rider-list-heading">
        YOUR CONVERSATIONS{" "}
        <span>{conversations.length.toString().padStart(2, "0")}</span>
      </div>
      <nav className="rider-conversation-list" aria-label="Conversations">
        {loading
          ? [1, 2, 3].map((n) => (
              <Skeleton key={n} className="rider-conversation-skeleton" />
            ))
          : filtered.map((c) => (
              <button
                key={c.id}
                className={`rider-conversation ${c.id === activeId ? "is-active" : ""}`}
                aria-current={c.id === activeId ? "page" : undefined}
                onClick={() => onSelect(c.id)}
              >
                <span className="rider-conversation-icon">
                  <MessageSquare size={16} />
                </span>
                <span className="rider-conversation-copy">
                  <strong>{c.title}</strong>
                  <span>{c.last_message}</span>
                  <span className="rider-conversation-meta">
                    <span
                      className={`rider-status-dot ${c.status.toLowerCase()}`}
                    />
                    {statusLabels[c.status]}
                    <time dateTime={c.updated_at}>
                      {relativeActivity(c.updated_at)}
                    </time>
                  </span>
                </span>
              </button>
            ))}
        {!loading && !filtered.length && (
          <p className="rider-sidebar-empty">
            {search
              ? "No matching conversations."
              : "No conversations yet. Start by describing a payout issue."}
          </p>
        )}
      </nav>
      <div className="rider-sidebar-bottom">
        <div>
          <ShieldCheck size={15} />
          <span>
            Private demo workspace<small>Sample data. No real payouts.</small>
          </span>
        </div>
        <Link href="/">
          <ArrowUpLeft size={14} />
          Back to QuickDrop
        </Link>
      </div>
    </div>
  );
}
