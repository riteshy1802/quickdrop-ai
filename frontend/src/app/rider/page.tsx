import type { Metadata } from "next";
import { RiderLayout } from "@/components/rider/rider-layout";
import "./rider.css";
export const metadata: Metadata = {
  title: "Rider Support - QuickDrop AI",
  description:
    "Explore QuickDrop AI Rider Support with illustrative payout conversations and dispute details.",
};
export default function RiderPage() {
  return <RiderLayout />;
}
