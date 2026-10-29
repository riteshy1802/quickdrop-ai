import { Sparkles } from "lucide-react";
import type { Scenario } from "@/types/rider";
export function ConversationEmptyState({
  creating,
}: {
  onScenario: (scenario: Scenario) => void;
  creating: boolean;
}) {
  return (
    <div className="rider-empty-state" aria-busy={creating}>
      <span className="rider-welcome-icon">
        <Sparkles size={29} />
      </span>
      <span className="rider-overline">YOUR PAYOUT. YOUR PEACE OF MIND.</span>
      <h2>Let’s get it sorted.</h2>
      <p>
        Missing surge? An incentive that didn’t arrive?
        <br />
        Tell us what happened, in your own words.
      </p>
      <small>
        Conversations and payment status are saved in your workspace.
      </small>
    </div>
  );
}
