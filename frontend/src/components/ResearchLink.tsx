import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Links to the instrument research page, or renders plain children when there is no symbol. */
export function ResearchLink({ symbol, children }: { symbol: string | null; children: ReactNode }) {
  if (!symbol) return <>{children}</>;
  return (
    <Link to={`/research/${encodeURIComponent(symbol)}`} className="underline">
      {children}
    </Link>
  );
}
