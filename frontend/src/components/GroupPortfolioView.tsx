// src/components/GroupPortfolioView.tsx
import { useEffect, useState } from "react";
import type { GroupPortfolio } from "../types";
import { HoldingsTable } from "./HoldingsTable";

const API = import.meta.env.VITE_API_URL ?? "";

type Props = {
  slug: string;           // "children" | "adults" | "all"
};

export function GroupPortfolioView({ slug }: Props) {
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  // fetch on mount or when slug changes
  useEffect(() => {
    if (!slug) return;

    fetch(`${API}/portfolio-group/${slug}`)
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.json();
      })
      .then(setPortfolio)
      .catch((e) => {
        console.error("failed to load group portfolio", e);
        setError(e.message);
      });
  }, [slug]);

  if (!slug) {
    return <p>Select a group.</p>;
  }

  if (error) {
    return <p style={{ color: "red" }}>Error: {error}</p>;
  }

  if (!portfolio) {
    return <p>Loading…</p>;
  }

  return (
    <div style={{ marginTop: "1rem" }}>
      <h2>{portfolio.name} — £{portfolio.total_value_estimate_gbp.toLocaleString()}</h2>

      {portfolio.accounts?.map((acct) => (
        <div key={acct.account_type} style={{ marginBottom: "1.5rem" }}>
          <h3>{acct.account_type} — £{acct.value_estimate_gbp.toLocaleString()}</h3>

          {/* holdings array might be missing; use ?. */}
          <HoldingsTable holdings={acct.holdings ?? []} />
        </div>
      ))}
    </div>
  );
}
