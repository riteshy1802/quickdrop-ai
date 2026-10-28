import {
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  Fingerprint,
  GitBranch,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
const steps = [
  {
    icon: MessageSquare,
    title: "Message Received",
    subtitle: "Intent & context captured",
    color: "cyan",
  },
  {
    icon: BrainCircuit,
    title: "AI Investigation",
    subtitle: "Trusted records retrieved",
    color: "violet",
  },
  {
    icon: ShieldCheck,
    title: "Policy Verification",
    subtitle: "Deterministic checks passed",
    color: "violet",
  },
  {
    icon: Wallet,
    title: "Payment Decision",
    subtitle: "Verified against PaySwift",
    color: "green",
  },
];
export function HeroWorkflowPreview() {
  return (
    <div className="workflow-preview">
      <div className="preview-toolbar">
        <div className="window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <span className="preview-title">
          <GitBranch size={13} aria-hidden="true" /> Resolution workspace
        </span>
        <span className="demo-badge">
          <span /> DEMONSTRATION DATA
        </span>
      </div>
      <div className="workflow-body">
        <div className="chat-panel">
          <div className="panel-label">
            <MessageSquare size={12} /> RIDER CONVERSATION{" "}
            <span className="live-dot" />
          </div>
          <div className="rider-profile">
            <div className="avatar">RK</div>
            <div>
              <strong>Rider R003</strong>
              <span>Hinglish · Payout inquiry</span>
            </div>
            <span className="profile-status">Online</span>
          </div>
          <div className="chat-bubble rider-bubble">
            <p>Bhai 20 tarikh ka surge nahi mila</p>
            <span>
              09:05 <CheckCheck size={12} />
            </span>
          </div>
          <div className="ai-message-label">
            <Sparkles size={12} /> QuickDrop AI
          </div>
          <div className="chat-bubble ai-bubble">
            <p>
              Samajh gaya. Main aapki trip aur surge payout check karta hoon.
            </p>
            <span>09:05</span>
          </div>
          <div className="context-tag">
            <Fingerprint size={12} /> Conversation context maintained
          </div>
        </div>
        <div className="workflow-panel">
          <div className="panel-label">
            <GitBranch size={12} /> RESOLUTION FLOW
          </div>
          <ol className="workflow-steps">
            {steps.map(({ icon: Icon, title, subtitle, color }, index) => (
              <li
                key={title}
                className={`workflow-step step-${index} ${color}`}
              >
                <span className="step-icon">
                  <Icon size={17} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <span>{subtitle}</span>
                </div>
                <Check size={13} className="step-check" aria-label="Complete" />
              </li>
            ))}
          </ol>
          <div className="policy-note">
            <ShieldCheck size={12} /> Governed by policy. Verified by code.
          </div>
        </div>
        <div className="decision-panel">
          <div className="panel-label">
            <CircleCheck size={12} /> VERIFIED OUTCOME
          </div>
          <div className="trip-row">
            <span>Trip reference</span>
            <strong>
              T926334 <ChevronRight size={13} />
            </strong>
          </div>
          <div className="amount-card">
            <span>Missing surge payout</span>
            <div>
              ₹25<span>.00</span>
              <span className="currency">INR</span>
            </div>
          </div>
          <dl className="verification-list">
            <div>
              <dt>Policy check</dt>
              <dd>
                <span className="tiny-dot" />
                Eligible
              </dd>
            </div>
            <div>
              <dt>Financial check</dt>
              <dd>
                <Check size={12} />
                Passed
              </dd>
            </div>
            <div>
              <dt>Approval</dt>
              <dd className="muted">Within auto-pay limit</dd>
            </div>
          </dl>
          <div className="payment-verified">
            <CircleCheck size={15} />
            <div>
              <strong>Payment verified</strong>
              <span>Sample PaySwift confirmation</span>
            </div>
            <ArrowRight size={14} />
          </div>
        </div>
      </div>
      <div className="preview-bottom">
        <span>
          <span className="tiny-dot" /> Every action has a trace
        </span>
        <span>
          COMPLAINT <ArrowRight size={10} /> CLARITY <ArrowRight size={10} />{" "}
          CONFIDENCE
        </span>
      </div>
    </div>
  );
}
