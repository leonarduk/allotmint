// src/components/GroupPortfolioView.tsx
import { useEffect, useState } from "react";
import type { GroupPortfolio } from "../types";
import { HoldingsTable } from "./HoldingsTable";

const API = import.meta.env.VITE_API_URL ?? "";

type Props = {
  slug: string;
  onSelectMember: (owner: string) => void;
};

export function GroupPortfolioView({ slug }: Props) {
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (!slug) return <p>Select a group.</p>;
  if (error) return <p style={{ color: "red" }}>Error: {error}</p>;
  if (!portfolio) return <p>Loading…</p>;

  // Calculate totals
  let totalValue = 0;
  let totalGain = 0;
  for (const acct of portfolio.accounts ?? []) {
    totalValue += acct.value_estimate_gbp ?? 0;
    for (const h of acct.holdings ?? []) {
      const cost =
        (h.cost_basis_gbp ?? 0) > 0
          ? h.cost_basis_gbp ?? 0
          : h.effective_cost_basis_gbp ?? 0;
      const market = h.market_value_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;
      totalGain += gain;
    }
  }

  return (
    <div style={{ marginTop: "1rem" }}>
      <h2>{portfolio.name}</h2>

      {/* Summary Box */}
      <div
        style={{
          display: "flex",
          gap: "2rem",
          marginBottom: "1rem",
          padding: "0.75rem 1rem",
          backgroundColor: "#222",
          border: "1px solid #444",
          borderRadius: "6px",
        }}
      >
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Total Value</div>
          <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>
            £{totalValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Total Gain</div>
          <div
            style={{
              fontSize: "1.2rem",
              fontWeight: "bold",
              color: totalGain >= 0 ? "lightgreen" : "red",
            }}
          >
            £{totalGain.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
        </div>
      </div>

      {/* Account breakdown */}
      {portfolio.accounts?.map((acct) => (
        <div key={acct.account_type} style={{ marginBottom: "1.5rem" }}>
          <h3>
            {acct.account_type} — £
            {acct.value_estimate_gbp.toLocaleString(undefined, {
              maximumFractionDigits: 2,
            })}
          </h3>
          <HoldingsTable holdings={acct.holdings ?? []} />
        </div>
      ))}
    </div>
  );
}
