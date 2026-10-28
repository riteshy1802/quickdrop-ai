import Link from "next/link";
import { Route } from "lucide-react";
export function Logo() {
  return (
    <Link href="/" className="brand" aria-label="QuickDrop AI home">
      <span className="brand-mark">
        <Route size={21} strokeWidth={2.3} aria-hidden="true" />
      </span>
      <span>
        QuickDrop<span className="brand-ai">AI</span>
      </span>
    </Link>
  );
}
