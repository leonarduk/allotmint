// src/components/GroupPortfolioView.tsx
import { useState } from "react";
import type { GroupPortfolio } from "../types";
import { getGroupPortfolio } from "../api";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money, percent } from "../lib/money";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";

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
  const { data: portfolio, loading, error } = useFetch<GroupPortfolio>(
    () => getGroupPortfolio(slug),
    [slug],
    !!slug
  );
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);

  /* ── early‑return states ───────────────────────────────── */
  if (!slug) return <p>Select a group.</p>;
  if (error) return <p style={{ color: "red" }}>Error: {error.message}</p>;
  if (loading || !portfolio) return <p>Loading…</p>;

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
      <table className={tableStyles.table} style={{ marginBottom: "1rem" }}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Owner</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total Value</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Day Change</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Day Change %</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total Gain</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total Gain %</th>
          </tr>
        </thead>
        <tbody>
          {ownerRows.map((row) => (
            <tr key={row.owner}>
              <td className={tableStyles.cell}>{row.owner}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(row.value)}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.dayChange >= 0 ? "lightgreen" : "red" }}
              >
                {money(row.dayChange)}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.dayChange >= 0 ? "lightgreen" : "red" }}
              >
                {percent(row.dayChangePct)}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.gain >= 0 ? "lightgreen" : "red" }}
              >
                {money(row.gain)}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.gain >= 0 ? "lightgreen" : "red" }}
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
            total_value_estimate_gbp={portfolio.total_value_estimate_gbp}
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
