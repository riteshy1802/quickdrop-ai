import { Route } from "lucide-react";
import { DemoLinks } from "@/components/shared/demo-links";
import { Reveal } from "@/components/shared/reveal";
export function FinalCTA() {
  return (
    <Reveal>
      <div className="final-cta">
        <div className="cta-orbit" aria-hidden="true">
          <Route size={25} />
        </div>
        <span className="section-kicker">THE NEXT STEP IS A CONVERSATION</span>
        <h2>
          See intelligent payout
          <br />
          resolution in action.
        </h2>
        <p>
          Experience the rider conversation and the operations
          <br className="desktop-break" /> workflow in one connected demo.
        </p>
        <DemoLinks final />
        <span className="cta-note">
          <span className="tiny-dot" /> Demo environment · No real money moves
        </span>
      </div>
    </Reveal>
  );
}
