import {
  Calculator,
  Check,
  CheckCheck,
  CircleCheck,
  CodeXml,
  MessagesSquare,
  ScanSearch,
  ShieldCheck,
  UserRoundCheck,
  Wallet,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Reveal } from "@/components/shared/reveal";
import { FinalCTA } from "./final-cta";
export function Capabilities() {
  return (
    <section
      id="capabilities"
      className="section capabilities-section"
      aria-labelledby="capabilities-title"
    >
      <div className="container">
        <Reveal>
          <div className="section-kicker">
            <span /> INTELLIGENCE, WITH GUARDRAILS
          </div>
          <div className="section-heading">
            <h2 id="capabilities-title">
              Built for accuracy.
              <br className="mobile-break" /> Designed for trust.
            </h2>
            <p>Everything a payout needs. Nothing left to guesswork.</p>
          </div>
        </Reveal>
        <div className="bento-grid">
          <Reveal className="bento-wide">
            <Card className="capability-card conversation-card">
              <div>
                <span className="feature-icon violet">
                  <MessagesSquare size={20} />
                </span>
                <h3>Multilingual AI conversations</h3>
                <p>
                  English, Hindi, or Hinglish. Multi-turn conversations with
                  contextual follow-ups that meet riders where they are.
                </p>
              </div>
              <div
                className="mini-chat"
                aria-label="Example multilingual conversation"
              >
                <div className="language-tabs">
                  <span>English</span>
                  <span>हिन्दी</span>
                  <span className="active">Hinglish</span>
                </div>
                <div className="mini-bubble">
                  Mera surge payout check kar do <CheckCheck size={12} />
                </div>
                <div className="mini-reply">
                  <span className="mini-spark">✧</span> Bilkul. Kaunsi trip ka
                  surge check karna hai?
                </div>
                <span className="mini-caption">
                  ONE CONVERSATION. FULL CONTEXT.
                </span>
              </div>
            </Card>
          </Reveal>
          <Reveal delay={0.08}>
            <Card className="capability-card calculation-card">
              <span className="feature-icon cyan">
                <Calculator size={20} />
              </span>
              <h3>Deterministic payout reconciliation</h3>
              <p>
                Base pay, distance, surge, incentives, and cancellation
                penalties. Calculated by code.
              </p>
              <div className="calculation-mini">
                <div>
                  <span>Expected payout</span>
                  <span>₹145.00</span>
                </div>
                <div>
                  <span>Actual payout</span>
                  <span>₹120.00</span>
                </div>
                <div className="calculation-result">
                  <span>Verified shortfall</span>
                  <strong>₹25.00</strong>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal>
            <Card className="capability-card">
              <span className="feature-icon cyan">
                <Wallet size={20} />
              </span>
              <h3>Safe payout execution</h3>
              <p>
                PaySwift integration with idempotency protection, retries,
                reconciliation, and visible payment status.
              </p>
              <div className="execution-mini">
                <div className="execution-header">
                  <span className="payswift-mark">
                    P<span>↗</span>
                  </span>
                  <strong>
                    PaySwift <span>Sandbox</span>
                  </strong>
                  <ShieldCheck size={16} />
                </div>
                <div className="execution-status">
                  <CircleCheck size={15} />
                  <span>Payment verified</span>
                  <span>₹25.00</span>
                </div>
                <div className="mini-caption">
                  <Check size={11} /> IDEMPOTENCY PROTECTED
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal delay={0.08}>
            <Card className="capability-card">
              <span className="feature-icon violet">
                <UserRoundCheck size={20} />
              </span>
              <h3>Human-in-the-loop operations</h3>
              <p>
                Approvals, escalations, and direct rider replies. Your team
                stays in control of sensitive payouts.
              </p>
              <div className="approval-mini">
                <div>
                  <span className="approval-avatar">OP</span>
                  <div>
                    <strong>Ops review required</strong>
                    <span>Repeat claim · Policy safeguard</span>
                  </div>
                  <span className="review-badge">Review</span>
                </div>
                <div className="approval-bottom">
                  <ShieldCheck size={13} />
                  <span>Human approval before payout</span>
                </div>
              </div>
            </Card>
          </Reveal>
          <Reveal delay={0.16}>
            <Card className="capability-card">
              <span className="feature-icon violet">
                <ScanSearch size={20} />
              </span>
              <h3>End-to-end auditability</h3>
              <p>
                Agent actions, tool calls, policy decisions, payments, and
                errors. Every step leaves a trace.
              </p>
              <div className="trace-mini">
                <div>
                  <span className="trace-dot" />
                  <code>trip_records.retrieved</code>
                  <span>09:05:01</span>
                </div>
                <div>
                  <span className="trace-dot" />
                  <code>policy.eligibility_passed</code>
                  <span>09:05:02</span>
                </div>
                <div>
                  <span className="trace-dot green" />
                  <code>payment.verified</code>
                  <span>09:05:03</span>
                </div>
                <span className="trace-link">
                  <CodeXml size={12} /> An explainable path to every outcome
                </span>
              </div>
            </Card>
          </Reveal>
        </div>
        <FinalCTA />
      </div>
    </section>
  );
}
