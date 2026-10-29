"use client";
import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  CheckCheck,
  CircleAlert,
  Clock3,
  RefreshCw,
  ShieldCheck,
  Wallet,
  Info,
} from "lucide-react";
import { Tooltip } from "radix-ui";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ColumnDef } from "@tanstack/react-table";
import type { OpsSnapshot } from "@/types/ops";
import { Button } from "@/components/ui/button";
import { DataTable } from "./data-table";
import {
  OpsData,
  PageHeading,
  Panel,
  StatusBadge,
  money,
  date,
} from "./common";
import { useOpsData } from "./use-ops";
export function OpsOverview() {
  return <OpsData>{(data) => <Overview data={data} />}</OpsData>;
}
function Overview({ data }: { data: OpsSnapshot }) {
  const [range, setRange] = useState("all"),
    query = useOpsData();
  const latest = Math.max(
    ...data.threads.map((t) =>
      Date.parse(t.messages[0]?.created_at ?? t.conversation.updated_at),
    ),
  );
  const threads = data.threads.filter(
    (t) =>
      range === "all" ||
      Date.parse(t.messages[0]?.created_at ?? t.conversation.updated_at) >=
        latest - 6 * 86400000,
  );
  const ids = new Set(threads.map((t) => t.conversation.id));
  const disputes = threads.flatMap((t) => t.disputes);
  const cases = data.cases.filter((c) => ids.has(c.conversation_id));
  const payouts = data.payouts.filter((p) => ids.has(p.conversation_id));
  const exceptions = payouts.filter((p) =>
    ["UNKNOWN", "FAILED", "NEEDS_REVIEW", "RECONCILIATION_PENDING"].includes(
      p.status,
    ),
  );
  const approved = new Set(
    cases.filter((c) => c.status === "APPROVED").map((c) => c.conversation_id),
  );
  const auto = threads.filter(
    (t) =>
      t.conversation.status === "RESOLVED" &&
      t.conversation.handler === "AI" &&
      t.conversation.resolved_by !== "OPS" &&
      !approved.has(t.conversation.id) &&
      t.disputes.some((d) => (d.verified_difference_rupees ?? 0) > 0),
  ).length;
  const noAdjustment = threads.filter(
    (t) =>
      t.disputes.length &&
      t.disputes.every((d) => d.verified_difference_rupees === 0),
  ).length;
  const human = threads.filter((t) => approved.has(t.conversation.id)).length;
  const distribution = [
    { name: "Auto-resolved", value: auto, color: "#7d91e1" },
    { name: "Human-approved", value: human, color: "#22d3ee" },
    { name: "No adjustment", value: noAdjustment, color: "#6ee7b7" },
    {
      name: "Other / escalated",
      value: Math.max(
        0,
        threads.filter((t) => t.disputes.length).length -
          auto -
          human -
          noAdjustment,
      ),
      color: "#d6b780",
    },
  ];
  const points = new Map<
    string,
    { day: string; received: number; resolved: number }
  >();
  if (Number.isFinite(latest))
    for (let days = 6; days >= 0; days--) {
      const day = new Date(latest - days * 86400000).toISOString().slice(0, 10);
      points.set(day, { day, received: 0, resolved: 0 });
    }
  for (const t of threads) {
    const day = (t.messages[0]?.created_at ?? t.conversation.updated_at).slice(
      0,
      10,
    );
    const point = points.get(day) ?? { day, received: 0, resolved: 0 };
    point.received += t.disputes.length;
    if (t.conversation.status === "RESOLVED")
      point.resolved += t.disputes.length;
    points.set(day, point);
  }
  const trend = [...points.values()].sort((a, b) => a.day.localeCompare(b.day));
  const rows = disputes.map((d) => ({
    ...d,
    rider_id: threads.find((t) => t.conversation.id === d.conversation_id)!
      .conversation.rider_id,
  }));
  type Row = (typeof rows)[number];
  const columns: ColumnDef<Row>[] = [
    {
      accessorKey: "id",
      header: "Dispute",
      cell: ({ row }) => (
        <Link
          className="ops-record-link"
          href={`/ops/conversations/${row.original.conversation_id}`}
        >
          {row.original.id}
        </Link>
      ),
    },
    { accessorKey: "rider_id", header: "Rider" },
    { accessorKey: "type", header: "Type" },
    {
      accessorKey: "verified_difference_rupees",
      header: "Verified",
      cell: ({ getValue }) => (
        <span className="ops-mono">{money(getValue<number>())}</span>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
    },
    {
      accessorKey: "relevant_date",
      header: "Payout date",
      cell: ({ getValue }) => date(getValue<string>()),
    },
  ];
  const metrics = [
    {
      label: "Total disputes",
      value: disputes.length,
      description: "Disputes in selected dates",
      icon: Activity,
    },
    {
      label: "AI auto-resolved",
      value: auto,
      description: "Resolved claims without human approval",
      icon: CheckCheck,
    },
    {
      label: "Pending approvals",
      value: cases.filter(
        (c) =>
          c.kind === "APPROVAL" && ["PENDING", "IN_REVIEW"].includes(c.status),
      ).length,
      description: "Approval cases still requiring a decision",
      icon: Clock3,
    },
    {
      label: "Active escalations",
      value: cases.filter(
        (c) =>
          c.kind === "ESCALATION" &&
          ["PENDING", "IN_REVIEW"].includes(c.status),
      ).length,
      description: "Unresolved human-review cases",
      icon: ShieldCheck,
    },
    {
      label: "Successfully paid",
      value: money(
        payouts
          .filter((p) => p.status === "SUCCEEDED")
          .reduce((sum, p) => sum + p.amount_rupees, 0),
      ),
      description: "Only provider-confirmed payments",
      icon: Wallet,
    },
    {
      label: "Payment exceptions",
      value: exceptions.length,
      description: "Unknown, failed, or review-required outcomes",
      icon: CircleAlert,
    },
  ];
  return (
    <>
      <PageHeading
        title="Operations Overview"
        description="Monitor rider disputes, agent resolution, and payment operations."
      >
        <select
          className="ops-select"
          aria-label="Overview date range"
          value={range}
          onChange={(e) => setRange(e.target.value)}
        >
          <option value="all">All dates</option>
          <option value="week">Latest 7 days</option>
        </select>
        <Button
          variant="outline"
          size="sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw size={14} />
          {query.isFetching ? "Refreshing…" : "Refresh"}
        </Button>
      </PageHeading>
      <Tooltip.Provider delayDuration={200}>
        <div className="ops-metrics">
          {metrics.map(({ label, value, description, icon: Icon }) => (
            <div className="ops-metric" key={label}>
              <div>
                <span>{label}</span>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <button aria-label={description}>
                      <Info size={12} />
                    </button>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content className="ops-tooltip" sideOffset={6}>
                      {description}
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              </div>
              <strong>{value}</strong>
              <span className="ops-metric-caption">
                <Icon size={12} />
                Sample records
              </span>
            </div>
          ))}
        </div>
      </Tooltip.Provider>
      <div className="ops-chart-grid">
        <Panel
          title="Dispute resolution trend"
          meta={<span className="ops-caption">Received vs. resolved</span>}
        >
          <div
            className="ops-chart"
            role="img"
            aria-label={`${disputes.length} disputes over ${trend.length} dates`}
          >
            <ResponsiveContainer width="100%" height={210}>
              <AreaChart
                data={trend}
                margin={{ top: 15, right: 18, left: -24, bottom: 0 }}
              >
                <CartesianGrid
                  vertical={false}
                  stroke="#272d3a"
                  strokeDasharray="3 3"
                />
                <XAxis
                  dataKey="day"
                  tick={{ fill: "#9ca3af", fontSize: 9 }}
                  tickFormatter={(v) => v.slice(5)}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: "#9ca3af", fontSize: 9 }}
                  axisLine={false}
                  tickLine={false}
                />
                <ChartTooltip
                  contentStyle={{
                    background: "#11151e",
                    border: "1px solid #272d3a",
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                />
                <Area
                  isAnimationActive={false}
                  name="Received"
                  type="monotone"
                  dataKey="received"
                  stroke="#748bdb"
                  fill="#4f5bd51a"
                  strokeWidth={2}
                />
                <Area
                  isAnimationActive={false}
                  name="Resolved"
                  type="monotone"
                  dataKey="resolved"
                  stroke="#6ee7b7"
                  fill="transparent"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Resolution distribution">
          <div className="ops-distribution">
            <div className="ops-donut">
              <ResponsiveContainer width="100%" height={145}>
                <PieChart>
                  <Pie
                    data={distribution.filter((d) => d.value)}
                    dataKey="value"
                    innerRadius={43}
                    outerRadius={62}
                    paddingAngle={4}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {distribution
                      .filter((d) => d.value)
                      .map((d) => (
                        <Cell key={d.name} fill={d.color} />
                      ))}
                  </Pie>
                  <ChartTooltip
                    contentStyle={{
                      background: "#11151e",
                      border: "1px solid #272d3a",
                      fontSize: 11,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <dl>
              {distribution.map((d) => (
                <div key={d.name}>
                  <dt>
                    <i style={{ background: d.color }} />
                    {d.name}
                  </dt>
                  <dd>{d.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Panel>
      </div>
      <Panel
        title="Recent disputes"
        meta={
          <Link href="/ops/conversations" className="ops-text-link">
            Open inbox →
          </Link>
        }
      >
        <DataTable
          data={rows}
          columns={columns}
          searchPlaceholder="Search disputes, rider, or type…"
        />
      </Panel>
      <div className="ops-bottom-grid">
        <Panel title="Payment exceptions">
          {exceptions.length ? (
            exceptions.map((p) => (
              <Link
                className="ops-exception-row"
                key={p.id}
                href={`/ops/payouts/${p.id}`}
              >
                <CircleAlert size={15} />
                <span>
                  <strong>
                    {p.rider_id} · {money(p.amount_rupees)}
                  </strong>
                  <small>
                    {p.attempts.at(-1)?.result ?? "No provider attempt"}
                  </small>
                </span>
                <StatusBadge status={p.status} />
              </Link>
            ))
          ) : (
            <p className="ops-panel-copy">
              No payment exceptions in this range.
            </p>
          )}
        </Panel>
        <Panel title="Recent activity">
          {data.traces
            .filter((t) => ids.has(t.conversation_id))
            .slice(0, 5)
            .map((t) => (
              <Link
                className="ops-activity-row"
                key={t.id}
                href={`/ops/audit?conversation=${t.conversation_id}`}
              >
                <span className="ops-activity-dot" />
                <span>
                  <strong>{t.name}</strong>
                  <small>
                    {t.rider_id} · {date(t.created_at)}
                  </small>
                </span>
              </Link>
            ))}
        </Panel>
      </div>
    </>
  );
}
