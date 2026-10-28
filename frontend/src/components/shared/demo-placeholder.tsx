import Link from "next/link";
import { ArrowLeft, MessageSquare, MonitorCog } from "lucide-react";
import { Logo } from "./logo";
export function DemoPlaceholder({ kind }: { kind: "rider" | "ops" }) {
  const rider = kind === "rider";
  const Icon = rider ? MessageSquare : MonitorCog;
  return (
    <div className="placeholder-page">
      <header className="container">
        <Logo />
        <Link href="/" className="back-link">
          <ArrowLeft size={15} /> Back to overview
        </Link>
      </header>
      <main className="placeholder-content">
        <span className="feature-icon violet">
          <Icon size={26} />
        </span>
        <span className="section-kicker">QUICKDROP AI · DEMO PREVIEW</span>
        <h1>
          {rider
            ? "A better conversation\nstarts here."
            : "Clarity for every\npayout decision."}
        </h1>
        <p>
          {rider
            ? "The Rider Experience is coming next: a multilingual conversation to report and understand payout issues."
            : "The Ops Console is coming next: a workspace for approvals, escalations, and complete resolution traces."}
        </p>
        <span className="placeholder-badge">
          In development · Interface preview only
        </span>
        <Link className="back-link" href="/">
          <ArrowLeft size={15} /> Explore QuickDrop AI
        </Link>
      </main>
      <footer>QuickDrop AI — Rider Payout Dispute Desk</footer>
    </div>
  );
}
