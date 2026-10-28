import type { Metadata } from "next";
import { OpsAuthProvider } from "@/components/ops/auth-context";
import "./ops.css";
export const metadata: Metadata = {
  title: "Operations Console — QuickDrop AI",
};
export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return <OpsAuthProvider>{children}</OpsAuthProvider>;
}
