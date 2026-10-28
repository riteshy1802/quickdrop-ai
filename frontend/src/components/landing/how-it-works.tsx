import {
  BrainCircuit,
  Check,
  MessageSquare,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Reveal } from "@/components/shared/reveal";
const stages = [
  {
    icon: MessageSquare,
    number: "01",
    title: "Rider reports",
    description: "A natural conversation. No forms, no friction.",
    points: [
      "Missing payouts, surge, incentives, or penalties",
      "English, Hindi, and Hinglish support",
      "Context maintained across messages",
    ],
    tag: "Start with a conversation",
    color: "cyan",
  },
  {
    icon: BrainCircuit,
    number: "02",
    title: "AI investigates",
    description: "Intelligent investigation. Grounded in real records.",
    points: [
      "Identifies the complaint and retrieves trusted records",
      "Policy engine calculates the exact shortfall",
      "Unclear claims go to your Ops team",
    ],
    tag: "AI reasoning + deterministic checks",
    color: "violet",
  },
  {
    icon: ShieldCheck,
    number: "03",
    title: "Resolve with confidence",
    description: "The right resolution, with the right oversight.",
    points: [
      "Eligible small payments processed automatically",
      "Larger or repeat claims require Ops approval",
      "PaySwift verification and a complete audit trail",
    ],
    tag: "Verified, explainable outcomes",
    color: "green",
  },
];
export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="section how-section"
      aria-labelledby="how-title"
    >
      <div className="container">
        <Reveal>
          <div className="section-kicker">
            <span /> THE RESOLUTION WORKFLOW
          </div>
          <div className="section-heading">
            <h2 id="how-title">From complaint to clarity.</h2>
            <p>
              A structured resolution workflow where every decision is
              explainable.
            </p>
          </div>
        </Reveal>
        <div className="stages-grid">
          {stages.map(
            (
              { icon: Icon, number, title, description, points, tag, color },
              index,
            ) => (
              <Reveal key={number} delay={index * 0.1}>
                <Card className={`stage-card ${color}`}>
                  <div className="stage-top">
                    <span className="feature-icon">
                      <Icon size={22} />
                    </span>
                    <span className="stage-number">{number}</span>
                  </div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                  <ul>
                    {points.map((point) => (
                      <li key={point}>
                        <Check size={13} aria-hidden="true" />
                        {point}
                      </li>
                    ))}
                  </ul>
                  <div className="stage-tag">
                    <span className="tiny-dot" />
                    {tag}
                  </div>
                </Card>
                {index < 2 && (
                  <span className="stage-connector" aria-hidden="true">
                    <ArrowRight size={14} />
                  </span>
                )}
              </Reveal>
            ),
          )}
        </div>
      </div>
    </section>
  );
}
