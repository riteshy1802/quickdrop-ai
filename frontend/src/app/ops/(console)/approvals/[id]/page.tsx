import { Suspense } from "react";
import { OpsCaseReview } from "@/components/ops/approvals";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsCaseReview />
    </Suspense>
  );
}
