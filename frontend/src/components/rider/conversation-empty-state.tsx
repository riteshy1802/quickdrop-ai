import {
  ArrowUpRight,
  Calculator,
  MessageSquare,
  Sparkles,
  UserRoundCheck,
  Wallet,
  CircleCheck,
} from "lucide-react";
import { scenarioLabels } from "@/lib/mock/rider-data";
import type { Scenario } from "@/types/rider";
const icons = {
  surge: Wallet,
  incentive: Sparkles,
  large: Calculator,
  correct: CircleCheck,
  human: UserRoundCheck,
  pending: MessageSquare,
};
export function ConversationEmptyState({
  onScenario,
  creating,
}: {
  onScenario: (scenario: Scenario) => void;
  creating: boolean;
}) {
  return (
    <div className="rider-empty-state">
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
      <div className="rider-scenario-heading">
        OR EXPLORE A SAMPLE CONVERSATION
      </div>
      <div className="rider-scenario-grid">
        {(Object.keys(scenarioLabels) as Scenario[]).map((scenario) => {
          const Icon = icons[scenario];
          return (
            <button
              key={scenario}
              disabled={creating}
              onClick={() => onScenario(scenario)}
            >
              <Icon size={16} />
              <span>{scenarioLabels[scenario]}</span>
              <ArrowUpRight size={13} />
            </button>
          );
        })}
      </div>
      <small>Scripted examples · Not assignment evaluation results</small>
    </div>
  );
}
