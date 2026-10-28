import { Suspense } from "react";
import { OpsApprovals } from "@/components/ops/approvals";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsApprovals />
    </Suspense>
  );
}
