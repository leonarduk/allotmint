// src/components/GroupPortfolioView.tsx
import { useEffect, useState } from "react";
import type { GroupPortfolio } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money, percent } from "../lib/money";

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
  let totalCost = 0;
  const perOwner: Record<string, { value: number; dayChange: number; gain: number; cost: number }> = {};

  for (const acct of portfolio.accounts ?? []) {
    const owner = acct.owner ?? "—";
    const entry =
      perOwner[owner] || (perOwner[owner] = { value: 0, dayChange: 0, gain: 0, cost: 0 });

    totalValue += acct.value_estimate_gbp ?? 0;
    entry.value += acct.value_estimate_gbp ?? 0;

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
      const dayChg = h.day_change_gbp ?? 0;

      totalCost += cost;
      totalGain += gain;
      totalDayChange += dayChg;

      entry.cost += cost;
      entry.gain += gain;
      entry.dayChange += dayChg;
    }
  }

  const totalGainPct = totalCost > 0 ? (totalGain / totalCost) * 100 : 0;
  const totalDayChangePct =
    totalValue - totalDayChange !== 0
      ? (totalDayChange / (totalValue - totalDayChange)) * 100
      : 0;
  const ownerRows = Object.entries(perOwner).map(([owner, data]) => {
    const gainPct = data.cost > 0 ? (data.gain / data.cost) * 100 : 0;
    const dayChangePct =
      data.value - data.dayChange !== 0
        ? (data.dayChange / (data.value - data.dayChange)) * 100
        : 0;
    return { owner, ...data, gainPct, dayChangePct };
  });

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
          <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>{money(totalValue)}</div>
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
            {money(totalDayChange)} ({percent(totalDayChangePct)})
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
            {money(totalGain)} ({percent(totalGainPct)})
          </div>
        </div>
      </div>

      {/* Per-owner summary */}
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          marginBottom: "1rem",
        }}
      >
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Owner</th>
            <th style={{ textAlign: "right" }}>Total Value</th>
            <th style={{ textAlign: "right" }}>Day Change</th>
            <th style={{ textAlign: "right" }}>Day Change %</th>
            <th style={{ textAlign: "right" }}>Total Gain</th>
            <th style={{ textAlign: "right" }}>Total Gain %</th>
          </tr>
        </thead>
        <tbody>
          {ownerRows.map((row) => (
            <tr key={row.owner}>
              <td>{row.owner}</td>
              <td style={{ textAlign: "right" }}>{money(row.value)}</td>
              <td
                style={{
                  textAlign: "right",
                  color: row.dayChange >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(row.dayChange)}
              </td>
              <td
                style={{
                  textAlign: "right",
                  color: row.dayChange >= 0 ? "lightgreen" : "red",
                }}
              >
                {percent(row.dayChangePct)}
              </td>
              <td
                style={{
                  textAlign: "right",
                  color: row.gain >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(row.gain)}
              </td>
              <td
                style={{
                  textAlign: "right",
                  color: row.gain >= 0 ? "lightgreen" : "red",
                }}
              >
                {percent(row.gainPct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Account breakdown */}
      {portfolio.accounts?.map((acct, idx) => (
        <div
          key={`${acct.owner ?? "owner"}-${acct.account_type}-${idx}`}
          style={{ marginBottom: "1.5rem" }}
        >
          <h3>
            {acct.owner ?? "—"} • {acct.account_type} — {money(acct.value_estimate_gbp)}
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
