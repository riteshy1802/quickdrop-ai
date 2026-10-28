import { Suspense } from "react";
import { OpsPayouts } from "@/components/ops/payouts";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsPayouts />
    </Suspense>
  );
}
