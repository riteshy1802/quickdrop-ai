import { Check, Clock3, CircleAlert } from "lucide-react";
import type { PaymentIntent } from "@/types/rider";
import { paymentLabels, money } from "./format";
export function PaymentTimeline({
  payment,
}: {
  payment: PaymentIntent | null;
}) {
  const status = payment?.status ?? "NOT_INITIATED";
  const steps =
    status === "SUCCEEDED"
      ? [
          "Adjustment approved",
          "Provider confirmation received",
          "Payment succeeded",
        ]
      : status === "RECONCILIATION_PENDING" || status === "UNKNOWN"
        ? [
            "Adjustment approved",
            "Submitted to provider",
            "Awaiting reconciliation",
          ]
        : status === "PROCESSING" || status === "PENDING"
          ? ["Adjustment approved", "Payment processing"]
          : status === "AWAITING_APPROVAL"
            ? ["Difference identified", "Awaiting human approval"]
            : status === "NEEDS_REVIEW"
              ? ["Adjustment verified", "Payment verification required"]
              : status === "FAILED"
              ? ["Payment could not be completed", "Support review required"]
              : ["Payment not initiated"];
  return (
    <div className="rider-payment">
      <div className="rider-detail-section-title">
        PAYMENT STATUS
        <span className={`rider-payment-state ${status.toLowerCase()}`}>
          {status === "SUCCEEDED" ? (
            <Check size={12} />
          ) : status === "FAILED" || status === "NEEDS_REVIEW" ? (
            <CircleAlert size={12} />
          ) : (
            <Clock3 size={12} />
          )}{" "}
          {paymentLabels[status]}
        </span>
      </div>
      {payment && (
        <div className="rider-payment-amount">
          {money(payment.amount_rupees)}
          <span>Sandbox payment amount</span>
        </div>
      )}
      <ol className="rider-payment-timeline">
        {steps.map((step, index) => (
          <li
            key={step}
            className={
              index === steps.length - 1 && status !== "SUCCEEDED"
                ? "is-pending"
                : "is-complete"
            }
          >
            <span>
              {index === steps.length - 1 && status !== "SUCCEEDED" ? (
                <Clock3 size={11} />
              ) : (
                <Check size={11} />
              )}
            </span>
            <div>
              {step}
              {index === steps.length - 1 && (
                <small>
                  {status === "SUCCEEDED"
                    ? "Confirmed by PaySwift sandbox"
                    : "No successful payment confirmed"}
                </small>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
