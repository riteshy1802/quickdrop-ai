import { Suspense } from "react";
import { OpsPayoutDetail } from "@/components/ops/payouts";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsPayoutDetail />
    </Suspense>
  );
}
