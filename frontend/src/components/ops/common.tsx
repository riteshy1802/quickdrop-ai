"use client";
import { Inbox, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type { OpsSnapshot } from "@/types/ops";
import { useOpsData } from "./use-ops";
export { money, date, time } from "@/components/rider/format";
export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant="outline"
      className={`ops-status status-${status.toLowerCase()}`}
    >
      {status.toLowerCase().replaceAll("_", " ")}
    </Badge>
  );
}
export function PageHeading({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="ops-page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children && <div className="ops-heading-actions">{children}</div>}
    </div>
  );
}
export function Panel({
  title,
  meta,
  children,
  className = "",
}: {
  title?: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`ops-panel ${className}`}>
      {title && (
        <header className="ops-panel-heading">
          <h2>{title}</h2>
          {meta}
        </header>
      )}
      {children}
    </section>
  );
}
export function EmptyState({
  title = "Nothing here yet.",
  description = "Try another filter or search term.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="ops-empty">
      <Inbox size={25} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function OpsData({
  children,
}: {
  children: (data: OpsSnapshot) => React.ReactNode;
}) {
  const query = useOpsData();
  if (query.isPending)
    return (
      <div
        className="ops-loading"
        role="status"
        aria-label="Loading operations data"
      >
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
    );
  if (query.isError)
    return (
      <div className="ops-empty" role="alert">
        <h2>Unable to load records.</h2>
        <p>{query.error.message}</p>
        <Button variant="outline" onClick={() => void query.refetch()}>
          <RotateCcw size={14} />
          Retry
        </Button>
      </div>
    );
  return children(query.data);
}
export function Feedback({
  error,
  success,
}: {
  error?: string;
  success?: boolean;
}) {
  return (
    <>
      {error && (
        <div className="ops-alert is-error" role="alert">
          {error}
        </div>
      )}
      {success && !error && (
        <div className="ops-toast" role="status">
          Demo workspace updated.
        </div>
      )}
    </>
  );
}
export function Segments<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; count?: number }[];
}) {
  return (
    <div className="ops-segments" role="group" aria-label="View filters">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          className={value === option.value ? "active" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && <span>{option.count}</span>}
        </button>
      ))}
    </div>
  );
}
