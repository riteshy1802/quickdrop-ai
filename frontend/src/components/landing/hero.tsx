import { ArrowDown, Check, Sparkles } from "lucide-react";
import { DemoLinks } from "@/components/shared/demo-links";
import { Reveal } from "@/components/shared/reveal";
import { HeroWorkflowPreview } from "./hero-workflow-preview";
export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-grid" aria-hidden="true" />
      <div className="container hero-inner">
        <Reveal>
          <div className="eyebrow-pill">
            <Sparkles size={13} aria-hidden="true" /> AI-Powered Payout
            Resolution <span className="pill-dot" />
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <h1 id="hero-title">
            Every payout dispute.
            <br />
            <span className="gradient-text">Resolved intelligently.</span>
          </h1>
        </Reveal>
        <Reveal delay={0.16}>
          <p className="hero-description">
            From rider complaints to verified payouts, QuickDrop combines
            conversational AI, deterministic financial checks, and human
            oversight to resolve disputes with confidence.
          </p>
        </Reveal>
        <Reveal delay={0.24}>
          <DemoLinks />
        </Reveal>
        <Reveal delay={0.3}>
          <ul className="hero-trust">
            {[
              "Multilingual Rider Support",
              "Policy-Governed Payouts",
              "Human-in-the-Loop",
            ].map((item) => (
              <li key={item}>
                <Check size={13} aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={0.35}>
          <HeroWorkflowPreview />
        </Reveal>
        <div className="hero-footnote">
          <span className="small-line" />
          AI understands the conversation. Code verifies the money.
          <span className="small-line" />
        </div>
        <a
          className="scroll-cue"
          href="#how-it-works"
          aria-label="Discover how QuickDrop works"
        >
          <ArrowDown size={16} />
        </a>
      </div>
    </section>
  );
}
