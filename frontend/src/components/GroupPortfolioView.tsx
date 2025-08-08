// src/components/GroupPortfolioView.tsx
import { useEffect, useState } from "react";
import type { GroupPortfolio } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";

/* ────────────────────────────────────────────────────────────
 * Small helpers
 * ────────────────────────────────────────────────────────── */
const fmt = (
  n?: number | null,
  opt?: Intl.NumberFormatOptions,
  dash: string = "—"
) =>
  typeof n === "number" && !Number.isNaN(n)
    ? n.toLocaleString("en-GB", opt)
    : dash;

const fmtGBP = (n?: number | null) => `£${fmt(n, { maximumFractionDigits: 2 })}`;

type SelectedInstrument = {
  ticker: string;
  name: string;
};

type Props = {
  slug: string;
  /** when clicking an owner you may want to jump to the member tab */
  onSelectMember?: (owner: string) => void;
};

/* ────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────── */
export function GroupPortfolioView({ slug }: Props) {
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);

  /* fetch portfolio whenever the slug changes */
  useEffect(() => {
    if (!slug) return;

    setError(null);
    setPortfolio(null);

    const API = import.meta.env.VITE_API_URL ?? "";

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

  /* ── early‑return states ───────────────────────────────── */
  if (!slug) return <p>Select a group.</p>;
  if (error) return <p style={{ color: "red" }}>Error: {error}</p>;
  if (!portfolio) return <p>Loading…</p>;

  /* ── aggregate totals for summary box ──────────────────── */
  let totalValue = 0;
  let totalGain = 0;
  let totalDayChange = 0;

  for (const acct of portfolio.accounts ?? []) {
    totalValue += acct.value_estimate_gbp ?? 0;

    for (const h of acct.holdings ?? []) {
      const cost =
        h.cost_basis_gbp && h.cost_basis_gbp > 0
          ? h.cost_basis_gbp
          : h.effective_cost_basis_gbp ?? 0;
      const market = h.market_value_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;

      totalGain += gain;
      totalDayChange += h.day_change_gbp ?? 0;
    }
  }

  /* ── render ────────────────────────────────────────────── */
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
          <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>{fmtGBP(totalValue)}</div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Day Change</div>
          <div
            style={{
              fontSize: "1.2rem",
              fontWeight: "bold",
              color: totalDayChange >= 0 ? "lightgreen" : "red",
            }}
          >
            {fmtGBP(totalDayChange)}
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
            {fmtGBP(totalGain)}
          </div>
        </div>
      </div>

      {/* Account breakdown */}
      {portfolio.accounts?.map((acct, idx) => (
        <div
          key={`${acct.owner ?? "owner"}-${acct.account_type}-${idx}`}
          style={{ marginBottom: "1.5rem" }}
        >
          <h3>
            {acct.owner ?? "—"} • {acct.account_type} — {fmtGBP(acct.value_estimate_gbp)}
          </h3>

          <HoldingsTable
            holdings={acct.holdings ?? []}
            onSelectInstrument={(ticker, name) => setSelected({ ticker, name })}
          />
        </div>
      ))}

      {/* Slide‑in instrument detail panel */}
      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default GroupPortfolioView;
