"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  CircleHelp,
  UserRoundCheck,
  X,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import type { OpsQueueItem, OpsSnapshot } from "@/types/ops";
import { Button } from "@/components/ui/button";
import { DataTable } from "./data-table";
import { ConfirmDialog } from "./confirm-dialog";
import {
  OpsData,
  PageHeading,
  Panel,
  Segments,
  StatusBadge,
  EmptyState,
  Feedback,
  money,
  date,
} from "./common";
import { useOpsAction } from "./use-ops";
export function OpsApprovals() {
  return <OpsData>{(data) => <CaseQueue data={data} />}</OpsData>;
}
function CaseQueue({ data }: { data: OpsSnapshot }) {
  const [tab, setTab] = useState("pending");
  const action = useOpsAction();
  const pending = data.cases.filter(
      (c) => c.kind === "APPROVAL" && c.status === "PENDING",
    ),
    escalations = data.cases.filter(
      (c) => c.kind === "ESCALATION" && c.status === "PENDING",
    ),
    review = data.cases.filter((c) => c.status === "IN_REVIEW"),
    history = data.cases.filter((c) =>
      ["APPROVED", "REJECTED", "RESOLVED"].includes(c.status),
    );
  const rows =
    tab === "pending"
      ? pending
      : tab === "escalations"
        ? escalations
        : tab === "review"
          ? review
          : history;
  const columns: ColumnDef<OpsQueueItem>[] = [
    {
      accessorKey: "id",
      header: "Case",
      cell: ({ row }) => (
        <Link
          className="ops-record-link"
          href={`/ops/approvals/${row.original.id}`}
        >
          {row.original.id}
        </Link>
      ),
    },
    { accessorKey: "rider_id", header: "Rider" },
    { accessorKey: "dispute_id", header: "Dispute" },
    {
      accessorKey: "amount_rupees",
      header: "Verified",
      cell: ({ getValue }) => (
        <span className="ops-mono">{money(getValue<number>())}</span>
      ),
    },
    {
      accessorKey: "reason",
      header: "Reason",
      cell: ({ getValue }) => (
        <span className="ops-table-reason">{getValue<string>()}</span>
      ),
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ getValue }) => date(getValue<string>()),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
    },
    {
      accessorKey: "assigned_to",
      header: "Assigned",
      cell: ({ getValue }) => getValue<string>() ?? "Unassigned",
    },
    {
      id: "actions",
      header: "Review",
      cell: ({ row }) => (
        <div className="ops-row-actions">
          <Link
            href={`/ops/approvals/${row.original.id}`}
            className="ops-text-link"
          >
            Review <ArrowUpRight size={12} />
          </Link>
          {row.original.kind === "ESCALATION" && row.original.status === "PENDING" && (
            <Button
              size="sm"
              variant="ghost"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({ type: "assign", id: row.original.id })
              }
            >
              Assign to me
            </Button>
          )}
        </div>
      ),
    },
  ];
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHeading
        title="Approvals & Escalations"
        description="Review the evidence. Make an explainable decision."
      />
      <div className="ops-inline-stats">
        <span>
          <strong>{pending.length}</strong>Pending approvals
        </span>
        <span>
          <strong>{escalations.length}</strong>Escalations
        </span>
        <span>
          <strong>{review.length}</strong>In review
        </span>
        <span>
          <strong>
            {history.filter((c) => c.reviewed_at?.startsWith(today)).length}
          </strong>
          Reviewed today
        </span>
      </div>
      <Segments
        value={tab}
        onChange={setTab}
        options={[
          {
            value: "pending",
            label: "Pending approvals",
            count: pending.length,
          },
          {
            value: "escalations",
            label: "Escalations",
            count: escalations.length,
          },
          { value: "review", label: "In review", count: review.length },
          { value: "history", label: "History", count: history.length },
        ]}
      />
      <Feedback error={action.error?.message} success={action.isSuccess} />
      <Panel>
        <DataTable
          data={rows}
          columns={columns}
          searchPlaceholder="Search case, rider, dispute, or reason…"
        />
      </Panel>
    </>
  );
}
export function OpsCaseReview() {
  const { id } = useParams<{ id: string }>();
  return <OpsData>{(data) => <CaseReview id={id} data={data} />}</OpsData>;
}
export function CaseReview({ id, data }: { id: string; data: OpsSnapshot }) {
  const action = useOpsAction();
  const item = data.cases.find((c) => c.id === id);
  if (!item)
    return (
      <EmptyState
        title="Case not found."
        description="Return to Approvals & Escalations to select an available case."
      />
    );
  const thread = data.threads.find(
    (t) => t.conversation.id === item.conversation_id,
  )!;
  const dispute = thread.disputes.find((d) => d.id === item.dispute_id)!;
  const closed = ["APPROVED", "REJECTED", "RESOLVED"].includes(item.status);
  // Evidence is advisory; the server always revalidates financial authorization.
  const failedEvidence = item.checks.some((c) => c.result === "FAILED");
  return (
    <>
      <PageHeading
        title={item.id}
        description={`${item.kind === "APPROVAL" ? "Payment approval" : "Escalation review"} · ${item.rider_id} · ${data.riders.find((r) => r.id === item.rider_id)?.name}`}
      >
        <Link className="ops-text-link" href="/ops/approvals">
          <ArrowLeft size={13} />
          Back to queue
        </Link>
        <StatusBadge status={item.status} />
      </PageHeading>
      <div className="ops-case-meta">
        <span>Created {date(item.created_at)}</span>
        <span>Assigned to {item.assigned_to ?? "no operator"}</span>
        <code>{item.dispute_id}</code>
      </div>
      <div className="ops-evidence-stats">
        {[
          { label: "Claimed amount", value: money(item.claimed_rupees) },
          { label: "Verified shortfall", value: money(item.amount_rupees) },
          {
            label: "Historically paid",
            value: money(dispute.historical_rupees),
          },
          {
            label: "Proposed payment",
            value:
              item.kind === "APPROVAL"
                ? money(item.amount_rupees)
                : "Not authorized",
          },
          {
            label: "Policy eligibility",
            value:
              item.kind === "APPROVAL"
                ? "Human approval required"
                : "Needs clarification",
          },
        ].map((stat) => (
          <div key={stat.label}>
            <span>{stat.label}</span>
            <strong>{stat.value}</strong>
          </div>
        ))}
      </div>
      <Feedback error={action.error?.message} success={action.isSuccess} />
      <div className="ops-case-grid">
        <div>
          <Panel
            title="Financial reconciliation"
            meta={<span className="ops-caption">Verified source records</span>}
          >
            <div className="ops-table-scroll">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Source / reference</th>
                    <th>Expected</th>
                    <th>Historical</th>
                    <th>Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {dispute.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.description}</strong>
                        <code>{row.trip_id ?? row.type}</code>
                      </td>
                      <td className="ops-mono">{money(row.expected_rupees)}</td>
                      <td className="ops-mono">
                        {money(row.historical_rupees)}
                      </td>
                      <td className="ops-mono">
                        {money(row.difference_rupees)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Verified total</td>
                    <td>{money(dispute.expected_rupees)}</td>
                    <td>{money(dispute.historical_rupees)}</td>
                    <td>{money(dispute.verified_difference_rupees)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Panel>
          <Panel title="Investigation summary">
            <div className="ops-panel-copy">
              <h3>{dispute.type}</h3>
              <p>{dispute.explanation}</p>
              <dl className="ops-detail-list">
                <div>
                  <dt>Policy flag</dt>
                  <dd>{item.reason}</dd>
                </div>
                <div>
                  <dt>Recommendation</dt>
                  <dd>
                    {item.kind === "APPROVAL"
                      ? "Review evidence before authorizing the exact shortfall."
                      : "Clarify the source data with the rider; no payout is authorized."}
                  </dd>
                </div>
                <div>
                  <dt>Historical date</dt>
                  <dd>{date(dispute.relevant_date)}</dd>
                </div>
              </dl>
              {item.rejection_reason && (
                <div className="ops-alert is-error">
                  Rejected: {item.rejection_reason}
                </div>
              )}
            </div>
          </Panel>
          <Panel
            title="Conversation context"
            meta={
              <Link
                href={`/ops/conversations/${item.conversation_id}`}
                className="ops-text-link"
              >
                Full conversation ↗
              </Link>
            }
          >
            <div className="ops-case-conversation">
              {thread.messages
                .filter((m) => m.visibility !== "INTERNAL" && !m.system_notice)
                .slice(0, 3)
                .map((m) => (
                  <div key={m.id}>
                    <strong>
                      {m.sender === "RIDER"
                        ? "Rider"
                        : m.sender === "OPS"
                          ? "Human Support"
                          : "AI Agent"}
                    </strong>
                    <p>{m.text}</p>
                  </div>
                ))}
            </div>
          </Panel>
        </div>
        <div>
          <Panel title="Policy verification">
            {item.checks.length === 0 && <p>Evidence checks unavailable</p>}
            <ul className="ops-policy-checklist">
              {item.checks.map((check) => (
                <li key={check.label}>
                  <span className={check.result.toLowerCase()}>
                    {check.result === "PASSED" ? (
                      <Check size={13} />
                    ) : check.result === "FAILED" ? (
                      <X size={13} />
                    ) : (
                      <CircleHelp size={13} />
                    )}
                  </span>
                  <div>
                    {check.label}
                    <small>
                      {check.result.toLowerCase().replaceAll("_", " ")}
                    </small>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Review decision">
            <div className="ops-decision-panel">
              <p>
                {closed
                  ? "This case has been reviewed. Its decision is recorded in the audit trail."
                  : item.kind === "APPROVAL"
                    ? "Approval authorizes a payment intent. It does not prove provider settlement."
                    : "Resolve the escalation only after the ambiguity has been addressed. Resolving does not issue money."}
              </p>
              {!closed && (
                <>
                  {item.kind === "ESCALATION" && <Button
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() =>
                      action.mutate({ type: "assign", id: item.id })
                    }
                  >
                    <UserRoundCheck size={14} />
                    Assign to me
                  </Button>}
                  {item.kind === "APPROVAL" ? (
                    <>
                      <ConfirmDialog
                        label="Approve payment"
                        title={`Approve ${money(item.amount_rupees)} for ${item.rider_id}?`}
                        description={`Authorize exactly ${money(item.amount_rupees)} for dispute ${item.dispute_id}. This authorizes a pending payment intent. Settlement requires PaySwift confirmation.`}
                        disabled={action.isPending || failedEvidence}
                        onConfirm={() =>
                          action.mutateAsync({ type: "approve", id: item.id })
                        }
                      />
                      <ConfirmDialog
                        label="Reject payment"
                        title={`Reject adjustment for ${item.rider_id}?`}
                        description="A reason is required and will be recorded with this decision."
                        reasonRequired
                        destructive
                        disabled={action.isPending}
                        onConfirm={(reason) =>
                          action.mutateAsync({
                            type: "reject",
                            id: item.id,
                            reason,
                          })
                        }
                      />
                    </>
                  ) : (
                    <>
                      <Link
                        href={`/ops/conversations/${item.conversation_id}`}
                        className="ops-button-link"
                      >
                        Contact rider / add internal note
                      </Link>
                      <ConfirmDialog
                        label="Mark resolved"
                        title="Resolve this escalation?"
                        description="Record that the ambiguity has been reviewed. This action never authorizes a payment."
                        disabled={action.isPending}
                        reasonRequired
                        onConfirm={(reason) =>
                          action.mutateAsync({
                            reason,
                            type: "resolve_case",
                            id: item.id,
                          })
                        }
                      />
                    </>
                  )}
                </>
              )}
              <Link
                className="ops-text-link"
                href={`/ops/audit?conversation=${item.conversation_id}`}
              >
                View decision audit →
              </Link>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
