import { Suspense } from "react";
import { OpsAudit } from "@/components/ops/audit";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsAudit />
    </Suspense>
  );
}
