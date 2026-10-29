"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import type { OpsPayout, OpsSnapshot } from "@/types/ops";
import { Button } from "@/components/ui/button";
import {
  OpsData,
  PageHeading,
  Panel,
  StatusBadge,
  EmptyState,
  Feedback,
  money,
  date,
  time,
} from "./common";
import { DataTable } from "./data-table";
import { useOpsAction } from "./use-ops";
export function OpsPayouts() {
  return <OpsData>{(data) => <PayoutList data={data} />}</OpsData>;
}
function PayoutList({ data }: { data: OpsSnapshot }) {
  const [status, setStatus] = useState("all"),
    [type, setType] = useState("all"),
    [rider, setRider] = useState(""),
    [min, setMin] = useState(""),
    [max, setMax] = useState(""),
    [range, setRange] = useState("all");
  const latest = Math.max(...data.payouts.map((p) => Date.parse(p.created_at)));
  const rows = data.payouts.filter(
    (p) =>
      (status === "all" || p.status === status) &&
      (type === "all" || p.initiation === type) &&
      p.rider_id.toLowerCase().includes(rider.toLowerCase()) &&
      (!min || p.amount_rupees >= Number(min)) &&
      (!max || p.amount_rupees <= Number(max)) &&
      (range === "all" || Date.parse(p.created_at) >= latest - 6 * 86400000),
  );
  const stats = [
    {
      label: "Authorized",
      value: money(
        data.payouts
          .filter((p) => p.status !== "AWAITING_APPROVAL")
          .reduce((sum, p) => sum + p.amount_rupees, 0),
      ),
    },
    {
      label: "Confirmed",
      value: money(
        data.payouts
          .filter((p) => p.status === "SUCCEEDED")
          .reduce((sum, p) => sum + p.amount_rupees, 0),
      ),
    },
    {
      label: "Processing / pending",
      value: data.payouts.filter((p) =>
        ["PENDING", "PROCESSING"].includes(p.status),
      ).length,
    },
    {
      label: "Unknown outcomes",
      value: data.payouts.filter((p) => p.status === "UNKNOWN").length,
    },
    {
      label: "Failed payments",
      value: data.payouts.filter((p) => p.status === "FAILED").length,
    },
    {
      label: "Pending reconciliation",
      value: data.payouts.filter((p) =>
        ["UNKNOWN", "RECONCILIATION_PENDING"].includes(p.status),
      ).length,
    },
  ];
  const columns: ColumnDef<OpsPayout>[] = [
    {
      accessorKey: "id",
      header: "Payment intent",
      cell: ({ row }) => (
        <Link
          href={`/ops/payouts/${row.original.id}`}
          className="ops-record-link"
        >
          {row.original.id}
        </Link>
      ),
    },
    { accessorKey: "rider_id", header: "Rider" },
    {
      accessorKey: "dispute_id",
      header: "Dispute",
      cell: ({ row }) => (
        <Link
          className="ops-text-link"
          href={`/ops/conversations/${row.original.conversation_id}`}
        >
          {row.original.dispute_id}
        </Link>
      ),
    },
    {
      accessorKey: "amount_rupees",
      header: "Amount",
      cell: ({ getValue }) => (
        <span className="ops-mono">{money(getValue<number>())}</span>
      ),
    },
    {
      accessorKey: "initiation",
      header: "Initiation",
      cell: ({ getValue }) =>
        getValue<string>().toLowerCase().replaceAll("_", " "),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
    },
    {
      accessorKey: "provider_id",
      header: "Provider ID",
      cell: ({ getValue }) => (
        <code>{getValue<string>() ?? "Not observed"}</code>
      ),
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ getValue }) => date(getValue<string>()),
    },
  ];
  const reconciled = data.payouts
    .filter((p) => p.reconciled_at)
    .sort(
      (a, b) => Date.parse(b.reconciled_at!) - Date.parse(a.reconciled_at!),
    )[0];
  return (
    <>
      <PageHeading
        title="Payouts & Reconciliation"
        description="Monitor authorized payouts and reconcile their status with PaySwift."
      />
      <div className="ops-inline-stats">
        {stats.map((s) => (
          <span key={s.label}>
            <strong>{s.value}</strong>
            {s.label}
          </span>
        ))}
      </div>
      <Panel>
        <div className="ops-filters">
          <select
            className="ops-select"
            aria-label="Payment status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {[
              "PENDING",
              "AWAITING_APPROVAL",
              "PROCESSING",
              "UNKNOWN",
              "SUCCEEDED",
              "FAILED",
              "NEEDS_REVIEW",
            ].map((s) => (
              <option key={s} value={s}>
                {s.toLowerCase().replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <select
            className="ops-select"
            aria-label="Payment initiation type"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="all">All payment types</option>
            <option value="AUTO">Automatic</option>
            <option value="HUMAN_APPROVED">Human approved</option>
          </select>
          <select
            className="ops-select"
            aria-label="Payment date range"
            value={range}
            onChange={(e) => setRange(e.target.value)}
          >
            <option value="all">All dates</option>
            <option value="week">Latest 7 days</option>
          </select>
          <input
            className="ops-filter-input"
            aria-label="Filter rider ID"
            placeholder="Rider ID"
            value={rider}
            onChange={(e) => setRider(e.target.value)}
          />
          <input
            className="ops-filter-input ops-amount-filter"
            aria-label="Minimum payment amount"
            type="number"
            min={0}
            placeholder="Min ₹"
            value={min}
            onChange={(e) => setMin(e.target.value)}
          />
          <input
            className="ops-filter-input ops-amount-filter"
            aria-label="Maximum payment amount"
            type="number"
            min={0}
            placeholder="Max ₹"
            value={max}
            onChange={(e) => setMax(e.target.value)}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatus("all");
              setType("all");
              setRange("all");
              setRider("");
              setMin("");
              setMax("");
            }}
          >
            Clear
          </Button>
        </div>
        <DataTable
          data={rows}
          columns={columns}
          searchPlaceholder="Search payment, rider, dispute, or provider…"
        />
      </Panel>
      <Panel title="PaySwift sandbox">
        <div className="ops-provider-health">
          <div>
            <span>Availability</span>
            <strong>Not monitored live</strong>
          </div>
          <div>
            <span>Last observed reconciliation</span>
            <strong>
              {reconciled
                ? `${date(reconciled.reconciled_at!)} · ${time(reconciled.reconciled_at!)}`
                : "No reconciliation observed"}
            </strong>
          </div>
          <div>
            <span>Outstanding unknowns</span>
            <strong>
              {data.payouts.filter((p) => p.status === "UNKNOWN").length}
            </strong>
          </div>
          <div>
            <span>Recorded provider errors</span>
            <strong>
              {
                data.payouts
                  .flatMap((p) => p.attempts)
                  .filter((a) => a.error_category).length
              }
            </strong>
          </div>
        </div>
      </Panel>
    </>
  );
}
export function OpsPayoutDetail() {
  const { id } = useParams<{ id: string }>();
  return <OpsData>{(data) => <PayoutDetail data={data} id={id} />}</OpsData>;
}
function PayoutDetail({ data, id }: { data: OpsSnapshot; id: string }) {
  const p = data.payouts.find((p) => p.id === id);
  const action = useOpsAction();
  if (!p)
    return (
      <EmptyState
        title="Payment not found."
        description="Select a payment intent from the Payouts table."
      />
    );
  return (
    <>
      <PageHeading
        title={p.id}
        description={`${p.rider_id} · ${money(p.amount_rupees)} · ${p.initiation.toLowerCase().replaceAll("_", " ")} · ${date(p.created_at)}`}
      >
        <Link className="ops-text-link" href="/ops/payouts">
          <ArrowLeft size={13} />
          All payouts
        </Link>
        <StatusBadge status={p.status} />
      </PageHeading>
      {p.status === "UNKNOWN" && (
        <div className="ops-alert">
          <ShieldAlert size={18} />
          <span>
            Payment outcome is uncertain. Verify the provider ledger before
            attempting another payout.
          </span>
        </div>
      )}
      <Feedback error={action.error?.message} success={action.isSuccess} />
      <div className="ops-payment-detail-grid">
        <Panel title="Observed lifecycle">
          <ol className="ops-payment-lifecycle">
            {p.lifecycle.map((event, index) => (
              <li key={`${event.name}-${index}`}>
                <i />
                <div>
                  <strong>{event.name}</strong>
                  <time>
                    {date(event.at)} · {time(event.at)}
                  </time>
                </div>
              </li>
            ))}
          </ol>
          <p className="ops-panel-note">
            Only recorded events are shown. Authorization is separate from
            provider settlement.
          </p>
        </Panel>
        <Panel title="Provider reconciliation">
          <div className="ops-panel-copy">
            <dl className="ops-detail-list">
              <div>
                <dt>Internal status</dt>
                <dd>
                  <StatusBadge status={p.status} />
                </dd>
              </div>
              <div>
                <dt>Last known provider status</dt>
                <dd>{p.provider_status}</dd>
              </div>
              <div>
                <dt>Provider payout ID</dt>
                <dd>{p.provider_id ?? "Not observed"}</dd>
              </div>
              <div>
                <dt>Last reconciliation</dt>
                <dd>
                  {p.reconciled_at ? date(p.reconciled_at) : "Not performed"}
                </dd>
              </div>
              <div>
                <dt>Outcome</dt>
                <dd>{p.reconciliation_outcome}</dd>
              </div>
            </dl>
            <Button
              variant="outline"
              disabled={
                action.isPending ||
                ["PENDING", "AWAITING_APPROVAL"].includes(p.status)
              }
              onClick={() => action.mutate({ type: "reconcile", id: p.id })}
            >
              <RefreshCw size={14} />
              {action.isPending ? "Reconciling…" : "Reconcile"}
            </Button>
            <small className="ops-muted">
              No payout is retried. A provider ledger lookup determines the
              observed status.
            </small>
          </div>
        </Panel>
      </div>
      <Panel title="PaySwift attempt history">
        <div className="ops-table-scroll">
          <table className="ops-table">
            <thead>
              <tr>
                {[
                  "Attempt",
                  "Request time",
                  "HTTP",
                  "Duration",
                  "Result",
                  "Retry scheduled",
                  "Error category",
                ].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {p.attempts.map((a) => (
                <tr key={a.number}>
                  <td>{a.number}</td>
                  <td>
                    {date(a.created_at)} {time(a.created_at)}
                  </td>
                  <td>
                    <code>{a.http_status ?? "No response"}</code>
                  </td>
                  <td>
                    {a.duration_ms === null ? "Unknown" : `${a.duration_ms} ms`}
                  </td>
                  <td>{a.result}</td>
                  <td>{a.retry_scheduled ? "Yes, recorded attempt" : "No"}</td>
                  <td>{a.error_category ?? "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!p.attempts.length && (
            <EmptyState
              title="No provider request submitted."
              description="This intent is awaiting approval or execution; no settlement is implied."
            />
          )}
        </div>
      </Panel>
      <div className="ops-related-links">
        <Link href={`/ops/conversations/${p.conversation_id}`}>
          Related dispute & conversation ↗
        </Link>
        <Link href={`/ops/audit?payment=${p.id}`}>Payment audit trace ↗</Link>
      </div>
    </>
  );
}
