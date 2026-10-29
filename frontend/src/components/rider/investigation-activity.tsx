"use client";

import { Check, ChevronDown, LoaderCircle } from "lucide-react";

export const activityLabels: Record<string, string> = {
  started: "Getting started",
  understanding_complaint: "Reading your message",
  checking_trip_records: "Checking trips",
  retrieving_payout_history: "Checking payments",
  calculating_verified_shortfall: "Comparing amounts",
  checking_payment_eligibility: "Checking the rules",
  authorizing_payment: "Checking approval",
  escalating_to_ops: "Asking support",
  preparing_response: "Writing your reply",
  verification_pending: "Check paused",
  retry_pending: "Trying again",
  investigation_failed: "Asking support to check",
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
        <span>{complete ? "View checks" : "Checking"}</span>
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
