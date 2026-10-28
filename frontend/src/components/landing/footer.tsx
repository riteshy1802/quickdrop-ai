import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Logo } from "@/components/shared/logo";
export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-main">
          <div className="footer-brand">
            <Logo />
            <p>
              AI-powered payout dispute resolution
              <br />
              with human oversight.
            </p>
          </div>
          <div className="footer-column">
            <h3>EXPLORE</h3>
            <Link href="/rider">
              Rider Demo <ArrowUpRight size={12} />
            </Link>
            <Link href="/ops">
              Ops Console <ArrowUpRight size={12} />
            </Link>
            <Link href="/#how-it-works">How it works</Link>
            <Link href="/#capabilities">Capabilities</Link>
          </div>
          <div className="footer-column">
            <h3>BUILT WITH</h3>
            <span>Next.js</span>
            <span>FastAPI</span>
            <span>PostgreSQL</span>
            <span>PaySwift Sandbox</span>
          </div>
          <div className="footer-philosophy">
            <span className="tiny-dot" />
            <span>
              Intelligent by design.
              <br />
              Accountable at every step.
            </span>
          </div>
        </div>
        <div className="footer-bottom">
          <span>QuickDrop AI — Rider Payout Dispute Desk</span>
          <span>AI reasoning. Deterministic decisions.</span>
        </div>
      </div>
    </footer>
  );
}
