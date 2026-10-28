"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "motion/react";
import {
  ArrowUpRight,
  FileText,
  MessageSquare,
  Search,
  Send,
  UserRoundCheck,
} from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import type { OpsSnapshot, WorkspaceThread } from "@/types/ops";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  OpsData,
  PageHeading,
  StatusBadge,
  Segments,
  Feedback,
  EmptyState,
  money,
  date,
  time,
} from "./common";
import { ConfirmDialog } from "./confirm-dialog";
import { AgentTraceTimeline } from "./trace-viewer";
import { useOpsAction } from "./use-ops";
export function OpsConversations() {
  return <OpsData>{(data) => <ConversationWorkspace data={data} />}</OpsData>;
}

function Composer({ thread }: { thread: WorkspaceThread }) {
  const action = useOpsAction();
  const [mode, setMode] = useState<"reply" | "note">("reply");
  const form = useForm<{ text: string }>({
    resolver: zodResolver(
      z.object({
        text: z
          .string()
          .trim()
          .min(1, "Enter a message.")
          .max(4000, "Keep messages below 4,000 characters."),
      }),
    ),
    defaultValues: { text: "" },
  });
  const canSend = mode === "note" || thread.conversation.handler === "OPS";
  async function send({ text }: { text: string }) {
    try {
      await action.mutateAsync({
        type: mode,
        id: thread.conversation.id,
        text,
      });
      form.reset();
    } catch {
      /* Error displayed below. */
    }
  }
  return (
    <form
      className={`ops-message-composer ${mode === "note" ? "is-note" : ""}`}
      onSubmit={form.handleSubmit(send)}
    >
      <div className="ops-composer-mode">
        <Segments
          value={mode}
          onChange={setMode}
          options={[
            { value: "reply", label: "Reply to rider" },
            { value: "note", label: "Internal note" },
          ]}
        />
        <span>
          {mode === "note"
            ? "Private · never shown to rider"
            : canSend
              ? "Human Support reply"
              : "Take over before replying"}
        </span>
      </div>
      <label className="sr-only" htmlFor="ops-reply-text">
        {mode === "note" ? "Internal note" : "Reply to rider"}
      </label>
      <Textarea
        id="ops-reply-text"
        {...form.register("text")}
        disabled={!canSend || action.isPending}
        placeholder={
          mode === "note"
            ? "Add context for your team…"
            : "Write a reply to the rider…"
        }
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void form.handleSubmit(send)();
          }
        }}
      />
      <div className="ops-composer-bottom">
        <span>
          {form.formState.errors.text?.message ??
            "Enter to send · Shift + Enter for a new line"}
        </span>
        <Button
          type="submit"
          className="ops-primary"
          size="sm"
          disabled={!canSend || action.isPending}
        >
          <Send size={13} />
          {action.isPending
            ? "Saving…"
            : mode === "note"
              ? "Save note"
              : "Send reply"}
        </Button>
      </div>
      <Feedback error={action.error?.message} />
    </form>
  );
}
function ThreadMessages({ thread }: { thread: WorkspaceThread }) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }, [thread.messages.length]);
  return (
    <div
      className="ops-thread-messages"
      role="log"
      aria-label="Operator conversation thread"
    >
      {thread.messages.map((m) =>
        m.system_notice ? (
          <div className="ops-thread-system" key={m.id}>
            {m.text}
          </div>
        ) : (
          <motion.article
            key={m.id}
            className={`ops-thread-message sender-${m.sender.toLowerCase()} ${m.visibility === "INTERNAL" ? "internal-note" : ""}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.18 }}
          >
            <div>
              <strong>
                {m.visibility === "INTERNAL" ? (
                  <>
                    <FileText size={12} />
                    Internal note
                  </>
                ) : m.sender === "RIDER" ? (
                  "Rider"
                ) : m.sender === "OPS" ? (
                  "Human Support"
                ) : (
                  "AI Agent"
                )}
              </strong>
              <time dateTime={m.created_at}>{time(m.created_at)}</time>
            </div>
            <p>{m.text}</p>
          </motion.article>
        ),
      )}
      {!thread.messages.length && (
        <EmptyState
          title="No messages yet."
          description="This rider has started a new conversation."
        />
      )}
      <div ref={bottom} />
    </div>
  );
}
function ContextPanel({
  thread,
  data,
}: {
  thread: WorkspaceThread;
  data: OpsSnapshot;
}) {
  const [tab, setTab] = useState<"rider" | "disputes" | "activity">("disputes");
  const rider = data.riders.find((r) => r.id === thread.conversation.rider_id);
  const joined: Record<string, string> = {
    R001: "2024-01-01",
    R003: "2024-03-15",
    R017: "2024-05-05",
  };
  return (
    <div className="ops-context-panel">
      <Segments
        value={tab}
        onChange={setTab}
        options={[
          { value: "rider", label: "Rider" },
          { value: "disputes", label: "Disputes" },
          { value: "activity", label: "Agent activity" },
        ]}
      />
      {tab === "rider" ? (
        <div className="ops-context-body">
          <span className="ops-avatar">
            {rider?.name
              .split(" ")
              .map((p) => p[0])
              .join("")}
          </span>
          <h3>{rider?.name}</h3>
          <dl className="ops-detail-list">
            <div>
              <dt>Rider</dt>
              <dd>{rider?.id}</dd>
            </div>
            <div>
              <dt>City</dt>
              <dd>{rider?.city}</dd>
            </div>
            <div>
              <dt>Joined</dt>
              <dd>
                {joined[rider?.id ?? ""]
                  ? date(joined[rider!.id])
                  : "Not provided"}
              </dd>
            </div>
            <div>
              <dt>Assigned operator</dt>
              <dd>{thread.conversation.assigned_operator ?? "Not assigned"}</dd>
            </div>
            <div>
              <dt>Referenced trips</dt>
              <dd>
                {thread.disputes
                  .flatMap((d) => d.items.map((i) => i.trip_id))
                  .filter(Boolean)
                  .join(", ") || "None"}
              </dd>
            </div>
          </dl>
        </div>
      ) : tab === "activity" ? (
        <div className="ops-context-body">
          <p className="ops-muted">
            Illustrative tool inputs and decisions. No private model reasoning.
          </p>
          <AgentTraceTimeline
            events={data.traces.filter(
              (t) => t.conversation_id === thread.conversation.id,
            )}
          />
        </div>
      ) : (
        <div className="ops-context-body">
          {thread.disputes.map((d) => (
            <div key={d.id} className="ops-context-dispute">
              <code>{d.id}</code>
              <h3>{d.type}</h3>
              <dl className="ops-detail-list">
                <div>
                  <dt>Expected</dt>
                  <dd>{money(d.expected_rupees)}</dd>
                </div>
                <div>
                  <dt>Historical paid</dt>
                  <dd>{money(d.historical_rupees)}</dd>
                </div>
                <div>
                  <dt>Verified shortfall</dt>
                  <dd className="ops-positive">
                    {money(d.verified_difference_rupees)}
                  </dd>
                </div>
                <div>
                  <dt>Payout date</dt>
                  <dd>{date(d.relevant_date)}</dd>
                </div>
                <div>
                  <dt>Payment</dt>
                  <dd>
                    <StatusBadge
                      status={d.payment?.status ?? "NOT_INITIATED"}
                    />
                  </dd>
                </div>
              </dl>
              <p>{d.explanation}</p>
              <details className="ops-source-records">
                <summary>Retrieved source records</summary>
                <div className="ops-mini-table">
                  <span>Source / reference</span>
                  <strong>Expected / actual</strong>
                  {d.items.map((item) => (
                    <div key={item.id}>
                      <code>{item.trip_id ?? item.type}</code>
                      <span>
                        {money(d.expected_rupees)} /{" "}
                        {money(d.historical_rupees)}
                      </span>
                    </div>
                  ))}
                </div>
                <small>
                  Illustrative fixture · not a live database result.
                </small>
              </details>
              {data.cases
                .filter((c) => c.dispute_id === d.id)
                .map((c) => (
                  <Link
                    className="ops-text-link"
                    key={c.id}
                    href={`/ops/approvals/${c.id}`}
                  >
                    Review {c.id} <ArrowUpRight size={12} />
                  </Link>
                ))}
              {d.payment && (
                <Link
                  className="ops-text-link"
                  href={`/ops/payouts/${d.payment.id}`}
                >
                  View payment lifecycle <ArrowUpRight size={12} />
                </Link>
              )}
            </div>
          ))}
          {!thread.disputes.length && (
            <EmptyState title="No dispute identified yet." />
          )}
        </div>
      )}
    </div>
  );
}
function ConversationWorkspace({ data }: { data: OpsSnapshot }) {
  const params = useParams<{ id?: string }>();
  const router = useRouter();
  const [selection, setSelection] = useState<{
    routeId?: string;
    id: string;
  }>();
  const [filter, setFilter] = useState("all"),
    [search, setSearch] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const action = useOpsAction();
  const activeId =
    (selection?.routeId === params.id ? selection?.id : undefined) ??
    params.id ??
    data.threads[0]?.conversation.id;
  const thread = data.threads.find((t) => t.conversation.id === activeId);
  const entries = data.threads.filter((t) => {
    const c = t.conversation;
    return (
      (filter === "all" ||
        (filter === "ai" && c.handler === "AI") ||
        (filter === "human" && c.handler === "OPS") ||
        (filter === "escalated" &&
          data.cases.some(
            (q) =>
              q.conversation_id === c.id &&
              q.kind === "ESCALATION" &&
              ["PENDING", "IN_REVIEW"].includes(q.status),
          )) ||
        (filter === "resolved" && c.status === "RESOLVED")) &&
      (
        c.id +
        " " +
        c.rider_id +
        " " +
        t.messages.map((m) => m.text).join(" ") +
        " " +
        t.disputes.flatMap((d) => d.items.map((i) => i.trip_id)).join(" ")
      )
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  });
  const list = (
    <div className="ops-inbox-list-inner">
      <label className="ops-search">
        <Search size={14} />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rider, trip, or message…"
          aria-label="Search inbox"
        />
      </label>
      <select
        className="ops-select"
        aria-label="Conversation handling filter"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      >
        <option value="all">All conversations</option>
        <option value="ai">AI handling</option>
        <option value="human">Human handling</option>
        <option value="escalated">Escalated</option>
        <option value="resolved">Resolved</option>
      </select>
      {entries.map((t) => {
        const c = t.conversation;
        const escalation = data.cases.some(
          (q) =>
            q.conversation_id === c.id &&
            q.kind === "ESCALATION" &&
            ["PENDING", "IN_REVIEW"].includes(q.status),
        );
        return (
          <button
            key={c.id}
            className={`ops-inbox-entry ${thread?.conversation.id === c.id ? "active" : ""}`}
            onClick={() => {
              setSelection({ routeId: params.id, id: c.id });
              if (params.id)
                router.replace(`/ops/conversations/${c.id}`, { scroll: false });
              setListOpen(false);
            }}
          >
            <div>
              <strong>{c.rider_id}</strong>
              <span>{time(c.updated_at)}</span>
            </div>
            <h3>{data.riders.find((r) => r.id === c.rider_id)?.name}</h3>
            <p>{c.last_message}</p>
            <div>
              <StatusBadge status={c.status} />
              <span>
                {escalation
                  ? "Escalated"
                  : c.handler === "OPS"
                    ? "Human"
                    : "AI"}
                {data.notifications.some(
                  (n) =>
                    !n.read &&
                    n.title === "New rider message" &&
                    n.href === `/ops/conversations/${c.id}`,
                ) && " · Unread"}
              </span>
            </div>
          </button>
        );
      })}
      {!entries.length && <EmptyState title="No matching conversations." />}
    </div>
  );
  if (!thread)
    return (
      <EmptyState
        title="Conversation not found."
        description="Return to the inbox to select an available record."
      />
    );
  const c = thread.conversation;
  return (
    <>
      <PageHeading
        title="Conversations"
        description="One inbox for AI and human-handled rider support."
      />
      <Feedback error={action.error?.message} success={action.isSuccess} />
      <div className="ops-inbox">
        <aside className="ops-inbox-list">{list}</aside>
        <section className="ops-inbox-thread">
          <header className="ops-thread-header">
            <div>
              <h2>
                {data.riders.find((r) => r.id === c.rider_id)?.name}
                <code>{c.rider_id}</code>
              </h2>
              <span>
                {c.handler === "OPS"
                  ? `Human Support · ${c.assigned_operator ?? "Unassigned"}`
                  : "AI handling"}
              </span>
            </div>
            <StatusBadge status={c.status} />
          </header>
          <div className="ops-thread-controls">
            <Button
              size="sm"
              variant="outline"
              className="ops-inbox-list-toggle"
              onClick={() => setListOpen(true)}
            >
              <MessageSquare size={13} />
              Inbox
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  type: c.handler === "OPS" ? "handoff" : "takeover",
                  id: c.id,
                })
              }
            >
              <UserRoundCheck size={13} />
              {c.handler === "OPS" ? "Return to AI" : "Take over"}
            </Button>
            <ConfirmDialog
              label="Resolve"
              title="Resolve this conversation?"
              description="This marks the conversation resolved. It does not settle an outstanding payment or approve a dispute."
              disabled={action.isPending || c.status === "RESOLVED"}
              onConfirm={() =>
                action.mutateAsync({ type: "resolve_conversation", id: c.id })
              }
            />
          </div>
          <ThreadMessages thread={thread} />
          <Composer key={c.id} thread={thread} />
        </section>
        <section
          className="ops-inbox-context"
          aria-label="Conversation details"
        >
          <ContextPanel key={c.id} thread={thread} data={data} />
        </section>
      </div>
      <Sheet open={listOpen} onOpenChange={setListOpen}>
        <SheetContent side="left" className="ops-detail-sheet">
          <SheetTitle>Conversations</SheetTitle>
          <SheetDescription>Select a rider thread.</SheetDescription>
          {list}
        </SheetContent>
      </Sheet>
    </>
  );
}
