import Link from "next/link";
import { ArrowUpRight, ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
export function DemoLinks({ final = false }: { final?: boolean }) {
  return (
    <div className="demo-links">
      <Link
        className={cn(buttonVariants({ size: "lg" }), "primary-button")}
        href="/rider"
      >
        {final ? "Try Rider Experience" : "Launch Rider Demo"}
        <ArrowUpRight size={17} aria-hidden="true" />
      </Link>
      <Link
        className={cn(
          buttonVariants({ variant: "outline", size: "lg" }),
          "secondary-button",
        )}
        href="/ops"
      >
        {final ? "Open Ops Console" : "Explore Ops Console"}
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </div>
  );
}
