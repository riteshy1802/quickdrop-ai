import { Suspense } from "react";
import { OpsConversations } from "@/components/ops/conversations";
export default function Page() {
  return (
    <Suspense
      fallback={<div className="ops-auth-loading">Loading workspace…</div>}
    >
      <OpsConversations />
    </Suspense>
  );
}
