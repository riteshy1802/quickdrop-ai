import { OpsShell } from "@/components/ops/ops-shell";
export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <OpsShell>{children}</OpsShell>;
}
