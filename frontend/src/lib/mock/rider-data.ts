import type {
  Conversation,
  ConversationStatus,
  Dispute,
  Message,
  PaymentStatus,
  PolicyStatus,
  Rider,
  Scenario,
} from "@/types/rider";

// Names and cities are copied from data/riders.csv. All conversations below are UI fixtures.
export const mockRiders: Rider[] = [
  { id: "R003", name: "Imran Khan", city: "Bengaluru", demo: true },
  { id: "R001", name: "Ravi Kumar", city: "Bengaluru", demo: true },
  { id: "R017", name: "Ramesh Babu", city: "Hyderabad", demo: true },
];
export const scenarioLabels: Record<Scenario, string> = {
  surge: "Missing surge",
  incentive: "Missing incentive",
  large: "Larger missing payment",
  correct: "Payout explained",
  human: "Human support",
  pending: "Payment pending",
};
export const scenarioPrompts: Record<Scenario, string> = {
  surge: "Bhai order T926334 ka surge nahi mila, 20 tarikh wala.",
  incentive: "19 September ka ₹150 incentive nahi mila. Please check.",
  large: "Mere payout mein ₹425 missing hai. Can you help?",
  correct: "Mera payout galat lag raha hai. Can you explain the amount?",
  human:
    "Meri trip details match nahi ho rahi. Support team se baat karni hai.",
  pending: "Mera ₹25 adjustment abhi tak nahi aaya. Payment ka status kya hai?",
};
interface Fixture {
  status: ConversationStatus;
  amount: number;
  expected: number;
  historical: number;
  approved: number | null;
  payment: PaymentStatus;
  policy: PolicyStatus;
  explanation: string;
  reply: string;
}
export const fixtures: Record<Scenario, Fixture> = {
  surge: {
    status: "RESOLVED",
    amount: 25,
    expected: 74,
    historical: 49,
    approved: 25,
    payment: "SUCCEEDED",
    policy: "AUTO_ELIGIBLE",
    explanation:
      "This sample surge adjustment is within the small-payment limit and has a simulated payment confirmation.",
    reply:
      "20 September ki trip T926334 par ₹74 expected tha aur ₹49 mila. ₹25 ka surge difference verified hai. Is demo mein payment confirmed dikhaya gaya hai — koi real payment nahi hua.",
  },
  incentive: {
    status: "RESOLVED",
    amount: 150,
    expected: 650,
    historical: 500,
    approved: 150,
    payment: "SUCCEEDED",
    policy: "AUTO_ELIGIBLE",
    explanation:
      "The illustrative incentive shortfall is eligible for a small automatic adjustment. The confirmation is simulated.",
    reply:
      "Is demo ke records mein ₹150 incentive ka difference hai. Sample adjustment confirmed hai. Yeh sirf demonstration hai; koi real payout process nahi hua.",
  },
  large: {
    status: "AWAITING_APPROVAL",
    amount: 425,
    expected: 925,
    historical: 500,
    approved: null,
    payment: "AWAITING_APPROVAL",
    policy: "OPS_APPROVAL",
    explanation:
      "₹425 exceeds the ₹200 automatic-payment limit. Human approval is required before any adjustment.",
    reply:
      "The sample records show a ₹425 difference. This exceeds the ₹200 automatic-payment limit, so it needs Ops approval. No payment has been initiated.",
  },
  correct: {
    status: "RESOLVED",
    amount: 0,
    expected: 120,
    historical: 120,
    approved: 0,
    payment: "NOT_INITIATED",
    policy: "AUTO_ELIGIBLE",
    explanation:
      "In this example, the historical payout matches the expected amount. No adjustment is owed.",
    reply:
      "In this sample, the expected payout and historical payout are both ₹120. The amounts match, so no adjustment is owed and no payment was created. Agar aapko koi specific trip galat lag rahi hai, uska ID share karein.",
  },
  human: {
    status: "HUMAN_HANDLING",
    amount: 25,
    expected: 74,
    historical: 49,
    approved: null,
    payment: "NOT_INITIATED",
    policy: "AWAITING_INFORMATION",
    explanation:
      "The sample trip information needs clarification. Human Support is reviewing it; the adjustment is not approved.",
    reply:
      "Hi, Human Support here. I’m reviewing this sample case. Please share the trip date and describe which details do not match. No payment has been initiated.",
  },
  pending: {
    status: "PAYMENT_PENDING",
    amount: 25,
    expected: 74,
    historical: 49,
    approved: 25,
    payment: "RECONCILIATION_PENDING",
    policy: "AUTO_ELIGIBLE",
    explanation:
      "The sample adjustment is approved, but provider reconciliation is still pending. It is not a successful payment yet.",
    reply:
      "Your sample ₹25 adjustment is approved, but confirmation is still pending reconciliation. It is not marked as successful. No real payment is being made in this demo.",
  },
};
export const seedTime = "2026-09-22T09:05:00+05:30";
export function makeScenario(
  id: string,
  riderId: string,
  scenario: Scenario,
  createdAt = seedTime,
): { conversation: Conversation; messages: Message[]; disputes: Dispute[] } {
  const fixture = fixtures[scenario];
  const disputeId = `DSP-${id}`;
  const isSurge =
    scenario === "surge" || scenario === "pending" || scenario === "human";
  const messages: Message[] = [
    {
      id: `${id}-r1`,
      conversation_id: id,
      sender: "RIDER",
      text: scenarioPrompts[scenario],
      created_at: createdAt,
      delivery: "DELIVERED",
    },
    {
      id: `${id}-a1`,
      conversation_id: id,
      sender: "AI",
      text: "I can help with that. This is an illustrative support conversation using sample records.",
      created_at: createdAt,
    },
  ];
  if (scenario === "human")
    messages.push({
      id: `${id}-notice`,
      conversation_id: id,
      sender: "AI",
      text: "Your conversation has been transferred to our support team.",
      created_at: createdAt,
      system_notice: true,
    });
  messages.push({
    id: `${id}-reply`,
    conversation_id: id,
    sender: scenario === "human" ? "OPS" : "AI",
    text: fixture.reply,
    created_at: createdAt,
  });
  return {
    conversation: {
      id,
      rider_id: riderId,
      title: scenarioLabels[scenario],
      status: fixture.status,
      handler: scenario === "human" ? "OPS" : "AI",
      updated_at: createdAt,
      last_message: fixture.reply,
      scenario,
    },
    messages,
    disputes: [
      {
        id: disputeId,
        conversation_id: id,
        type: scenarioLabels[scenario],
        relevant_date: scenario === "incentive" ? "2026-09-19" : "2026-09-20",
        status: fixture.status,
        policy: fixture.policy,
        explanation: fixture.explanation,
        expected_rupees: fixture.expected,
        historical_rupees: fixture.historical,
        verified_difference_rupees: fixture.amount,
        approved_adjustment_rupees: fixture.approved,
        items: [
          {
            id: `${id}-item`,
            type:
              scenario === "incentive"
                ? "INCENTIVE"
                : isSurge
                  ? "SURGE"
                  : "PAYOUT",
            trip_id: isSurge ? "T926334" : null,
            description: scenarioLabels[scenario],
            difference_rupees: fixture.amount,
          },
        ],
        payment:
          fixture.payment === "NOT_INITIATED"
            ? null
            : {
                id: `PAY-${id}`,
                dispute_id: disputeId,
                amount_rupees: fixture.amount,
                status: fixture.payment,
                updated_at: createdAt,
              },
      },
    ],
  };
}
export const seedAssignments: [string, string, Scenario][] = [
  ["QD-1003", "R003", "surge"],
  ["QD-1004", "R003", "pending"],
  ["QD-1001", "R001", "incentive"],
  ["QD-1002", "R001", "correct"],
  ["QD-1017", "R017", "large"],
  ["QD-1018", "R017", "human"],
];
