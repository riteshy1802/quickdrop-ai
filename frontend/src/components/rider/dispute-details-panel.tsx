import { FileCheck2, ShieldCheck, X, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Dispute } from "@/types/rider";
import { date, money, policyLabels } from "./format";
import { PaymentTimeline } from "./payment-timeline";
export function DisputeDetailsPanel({
  disputes,
  loading,
  onClose,
}: {
  disputes: Dispute[];
  loading: boolean;
  onClose?: () => void;
}) {
  return (
    <div className="rider-details-inner">
      <header className="rider-details-header">
        <div>
          <FileCheck2 size={16} />
          <h2>Dispute details</h2>
        </div>
        {onClose && (
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Close dispute details"
            onClick={onClose}
          >
            <X size={16} />
          </Button>
        )}
      </header>
      <div className="rider-details-content">
        <div className="rider-details-demo">
          <Info size={13} />
          <span>
            Saved dispute records.
            <br />
            Payment status follows provider confirmation.
          </span>
        </div>
        {loading ? (
          <>
            <Skeleton className="rider-detail-skeleton" />
            <Skeleton className="rider-detail-skeleton" />
          </>
        ) : !disputes.length ? (
          <div className="rider-details-empty">
            <FileCheck2 size={27} />
            <h3>A little context first.</h3>
            <p>
              Dispute and payout details appear as your concern is investigated.
            </p>
          </div>
        ) : (
          disputes.map((dispute) => (
            <article key={dispute.id} className="rider-dispute">
              <div className="rider-detail-section-title">DISPUTE SUMMARY</div>
              <h3>{dispute.type}</h3>
              <dl className="rider-detail-list">
                <div>
                  <dt>Dispute ID</dt>
                  <dd>{dispute.id}</dd>
                </div>
                <div>
                  <dt>Related trips</dt>
                  <dd>
                    {dispute.items
                      .map((item) => item.trip_id)
                      .filter(Boolean)
                      .join(", ") || "Not specified"}
                  </dd>
                </div>
                <div>
                  <dt>Opened on</dt>
                  <dd>{date(dispute.relevant_date)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{dispute.status.toLowerCase().replaceAll("_", " ")}</dd>
                </div>
              </dl>
              <div className="rider-breakdown">
                <div className="rider-detail-section-title">
                  PAYOUT BREAKDOWN
                </div>
                <dl>
                  <div>
                    <dt>Expected payout</dt>
                    <dd>{money(dispute.expected_rupees)}</dd>
                  </div>
                  <div>
                    <dt>Historical payout</dt>
                    <dd>{money(dispute.historical_rupees)}</dd>
                  </div>
                  <div className="rider-verified-difference">
                    <dt>Verified difference</dt>
                    <dd>{money(dispute.verified_difference_rupees)}</dd>
                  </div>
                  <div>
                    <dt>Approved adjustment</dt>
                    <dd>
                      {dispute.approved_adjustment_rupees === null
                        ? "Not approved"
                        : money(dispute.approved_adjustment_rupees)}
                    </dd>
                  </div>
                  <div>
                    <dt>Payment amount</dt>
                    <dd>
                      {dispute.payment
                        ? money(dispute.payment.amount_rupees)
                        : "Not initiated"}
                    </dd>
                  </div>
                </dl>
              </div>
              <div className="rider-policy-context">
                <ShieldCheck size={16} />
                <div>
                  <strong>{policyLabels[dispute.policy]}</strong>
                  <p>{dispute.explanation}</p>
                </div>
              </div>
              <PaymentTimeline payment={dispute.payment} />
            </article>
          ))
        )}
      </div>
      <div className="rider-details-footer">
        <ShieldCheck size={13} />
        AI understands. Code verifies.
      </div>
    </div>
  );
}
