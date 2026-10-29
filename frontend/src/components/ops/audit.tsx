"use client";
import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SlidersHorizontal } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import type { AgentTrace, OpsSnapshot } from "@/types/ops";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  OpsData,
  PageHeading,
  Panel,
  Segments,
  StatusBadge,
  EmptyState,
  date,
  time,
} from "./common";
import { DataTable } from "./data-table";
import { AgentTraceTimeline, TraceJsonViewer } from "./trace-viewer";
export function OpsAudit() {
  return <OpsData>{(data) => <AuditExplorer data={data} />}</OpsData>;
}
function AuditExplorer({ data }: { data: OpsSnapshot }) {
  const search = useSearchParams();
  const [mode, setMode] = useState("table"),
    [selected, setSelected] = useState<string | null>(null);
  const [rider, setRider] = useState(""),
    [conversation, setConversation] = useState(
      search.get("conversation") ?? "",
    ),
    [dispute, setDispute] = useState(""),
    [payment, setPayment] = useState(search.get("payment") ?? ""),
    [type, setType] = useState("all"),
    [status, setStatus] = useState("all"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const rows = data.traces.filter(
    (t) =>
      (!rider || t.rider_id.toLowerCase().includes(rider.toLowerCase())) &&
      (!conversation ||
        t.conversation_id.toLowerCase().includes(conversation.toLowerCase())) &&
      (!dispute ||
        t.dispute_id?.toLowerCase().includes(dispute.toLowerCase())) &&
      (!payment || t.payment_id === payment) &&
      (type === "all" || t.type === type) &&
      (status === "all" || t.status === status) &&
      (!from || Date.parse(t.created_at) >= Date.parse(from + "+05:30")) &&
      (!to || Date.parse(t.created_at) <= Date.parse(to + "+05:30")),
  );
  const event = data.traces.find((t) => t.id === selected);
  const columns: ColumnDef<AgentTrace>[] = [
    {
      accessorKey: "created_at",
      header: "Timestamp",
      cell: ({ getValue }) => (
        <span className="ops-mono">
          {date(getValue<string>())} {time(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: "type",
      header: "Event type",
      cell: ({ getValue }) => <code>{getValue<string>()}</code>,
    },
    { accessorKey: "rider_id", header: "Rider" },
    {
      accessorKey: "conversation_id",
      header: "Conversation",
      cell: ({ getValue }) => (
        <Link
          href={`/ops/conversations/${getValue<string>()}`}
          className="ops-record-link"
        >
          {getValue<string>()}
        </Link>
      ),
    },
    { accessorKey: "name", header: "Event" },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
    },
    {
      id: "details",
      header: "Details",
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSelected(row.original.id)}
        >
          Inspect →
        </Button>
      ),
    },
  ];
  const groups = [...new Set(rows.map((t) => t.conversation_id))];
  const applied =
    [rider, conversation, dispute, payment, from, to].filter(Boolean).length +
    Number(type !== "all") +
    Number(status !== "all");
  return (
    <>
      <PageHeading
        title="Audit & Agent Traces"
        description="Inspect message processing, policy decisions, and observed payment events."
      />
      <div className="ops-audit-toolbar">
        <Segments
          value={mode}
          onChange={setMode}
          options={[
            { value: "table", label: "Events" },
            { value: "timeline", label: "Timeline" },
          ]}
        />
        <span className="ops-caption">
          Sanitized fixture data · No private model reasoning
        </span>
      </div>
      <Panel>
        <details className="ops-advanced-filters" open={applied > 0}>
          <summary>
            <SlidersHorizontal size={13} />
            Filters{applied > 0 && <span>{applied} applied</span>}
          </summary>
          <div className="ops-filters">
            <input
              className="ops-filter-input"
              aria-label="Audit rider ID"
              placeholder="Rider ID"
              value={rider}
              onChange={(e) => setRider(e.target.value)}
            />
            <input
              className="ops-filter-input"
              aria-label="Audit conversation ID"
              placeholder="Conversation ID"
              value={conversation}
              onChange={(e) => setConversation(e.target.value)}
            />
            <input
              className="ops-filter-input"
              aria-label="Audit dispute ID"
              placeholder="Dispute ID"
              value={dispute}
              onChange={(e) => setDispute(e.target.value)}
            />
            <input
              className="ops-filter-input"
              aria-label="Audit payment intent ID"
              placeholder="Payment intent ID"
              value={payment}
              onChange={(e) => setPayment(e.target.value)}
            />
            <select
              className="ops-select"
              aria-label="Event type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="all">All event types</option>
              {[...new Set(data.traces.map((t) => t.type))].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              className="ops-select"
              aria-label="Event status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="OK">OK</option>
              <option value="PENDING">Pending</option>
              <option value="ERROR">Error</option>
            </select>
            <label className="ops-date-field">
              From · IST
              <input
                type="datetime-local"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="ops-date-field">
              To · IST
              <input
                type="datetime-local"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setRider("");
                setConversation("");
                setDispute("");
                setPayment("");
                setType("all");
                setStatus("all");
                setFrom("");
                setTo("");
              }}
            >
              Clear filters
            </Button>
          </div>
        </details>
        {mode === "table" ? (
          <DataTable
            data={rows}
            columns={columns}
            searchPlaceholder="Search trace names, categories, or IDs…"
          />
        ) : (
          <div className="ops-audit-timelines">
            {groups.map((id) => (
              <section key={id}>
                <h2>
                  <Link
                    className="ops-record-link"
                    href={`/ops/conversations/${id}`}
                  >
                    {id}
                  </Link>
                </h2>
                <AgentTraceTimeline
                  events={rows.filter((t) => t.conversation_id === id)}
                />
              </section>
            ))}
            {!groups.length && (
              <EmptyState title="No events match these filters." />
            )}
          </div>
        )}
      </Panel>
      <Sheet
        open={!!event}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="ops-detail-sheet ops-trace-sheet">
          <SheetTitle>{event?.name ?? "Trace details"}</SheetTitle>
          <SheetDescription>
            Sanitized event metadata and recorded tool payloads.
          </SheetDescription>
          {event && (
            <>
              <dl className="ops-detail-list">
                <div>
                  <dt>Event ID</dt>
                  <dd>{event.id}</dd>
                </div>
                <div>
                  <dt>Correlation ID</dt>
                  <dd>{event.correlation_id}</dd>
                </div>
                <div>
                  <dt>Timestamp</dt>
                  <dd>
                    {date(event.created_at)} {time(event.created_at)}
                  </dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge status={event.status} />
                  </dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>
                    {event.duration_ms === null
                      ? "Not recorded"
                      : `${event.duration_ms} ms`}
                  </dd>
                </div>
              </dl>
              <TraceJsonViewer
                value={{ input: event.input, output: event.output }}
              />
              <Link
                href={`/ops/conversations/${event.conversation_id}`}
                className="ops-text-link"
                onClick={() => setSelected(null)}
              >
                Open related conversation ↗
              </Link>
              {event.payment_id && (
                <Link
                  href={`/ops/payouts/${event.payment_id}`}
                  className="ops-text-link"
                  onClick={() => setSelected(null)}
                >
                  Open related payment ↗
                </Link>
              )}
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
