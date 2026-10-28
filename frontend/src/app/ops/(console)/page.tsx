import { Suspense } from "react";
import { OpsOverview } from "@/components/ops/overview";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsOverview />
    </Suspense>
  );
}
