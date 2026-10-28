import { OpsAuthProvider } from "@/components/ops/auth-context";
// @ts-expect-error Next.js handles this global stylesheet import at runtime.
import "./ops.css";
export const metadata = {
  title: "Operations Console - QuickDrop AI",
};
export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return <OpsAuthProvider>{children}</OpsAuthProvider>;
}
