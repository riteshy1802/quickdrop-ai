"use client";

import { Check, ChevronDown, LoaderCircle } from "lucide-react";

export const activityLabels: Record<string, string> = {
  started: "Starting investigation",
  understanding_complaint: "Understanding your complaint",
  checking_trip_records: "Checking your trip records",
  retrieving_payout_history: "Retrieving payout history",
  calculating_verified_shortfall: "Reconciling expected and recorded pay",
  checking_payment_eligibility: "Checking eligibility",
  authorizing_payment: "Checking payment authorization",
  escalating_to_ops: "Requesting support review",
  preparing_response: "Preparing your answer",
  verification_pending: "Verification saved; waiting to resume",
  retry_pending: "Verification will retry",
  investigation_failed: "Investigation unavailable; requesting support review",
};

export function InvestigationActivity({ activity, complete }: {
  activity: string[];
  complete: boolean;
}) {
  const steps = activity.filter((step) => activityLabels[step]);
  if (!steps.length) return null;
  return (
    <details className="rider-investigation" open={!complete}>
      <summary>
        {complete ? <Check size={14} /> : <LoaderCircle size={14} className="rider-activity-spinner" />}
        <span>{complete ? "Investigation activity" : "Investigating"}</span>
        <ChevronDown size={14} />
      </summary>
      <ol aria-label="Investigation steps">
        {steps.map((step, index) => (
          <li key={step}>
            {complete || index < steps.length - 1 ? <Check size={12} /> : <LoaderCircle size={12} />}
            {activityLabels[step]}
          </li>
        ))}
      </ol>
    </details>
  );
}
