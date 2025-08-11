// src/components/GroupPortfolioView.tsx
import { useState, useEffect } from "react";
import type { GroupPortfolio, Account } from "../types";
import { getGroupPortfolio } from "../api";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { money, percent } from "../lib/money";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";

const PIE_COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff8042",
  "#8dd1e1",
  "#a4de6c",
  "#d0ed57",
  "#ffc0cb",
];

type SelectedInstrument = {
  ticker: string;
  name: string;
};

type Props = {
  slug: string;
  /** when clicking an owner you may want to jump to the member tab */
  onSelectMember?: (owner: string) => void;
  /**
   * Toggle for displaying absolute columns like Units/Cost/Gain in the
   * holdings tables. When true, those columns are hidden to show relative
   * percentages instead.
   */
  relativeView?: boolean;
};

/* ────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────── */
export function GroupPortfolioView({ slug, relativeView }: Props) {
  const { data: portfolio, loading, error } = useFetch<GroupPortfolio>(
    () => getGroupPortfolio(slug),
    [slug],
    !!slug
  );
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);

  // helper to derive a stable key for each account
  const accountKey = (acct: Account, idx: number) =>
    `${acct.owner ?? "owner"}-${acct.account_type}-${idx}`;

  // when portfolio changes, select all accounts by default
  useEffect(() => {
    if (portfolio?.accounts) {
      setSelectedAccounts(portfolio.accounts.map(accountKey));
    }
  }, [portfolio]);

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
  const perType: Record<string, number> = {};

  const formatType = (t: string | null | undefined) => {
    if (!t) return "Other";
    const normalized = t.toLowerCase().replace(/_/g, " ");
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
  };

  const activeKeys = selectedAccounts.length
    ? new Set(selectedAccounts)
    : new Set(portfolio.accounts?.map(accountKey));

  for (const [idx, acct] of (portfolio.accounts ?? []).entries()) {
    const key = accountKey(acct, idx);
    if (!activeKeys.has(key)) continue;
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

      const type = formatType(h.instrument_type);
      perType[type] = (perType[type] || 0) + market;

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

  const typeRows = Object.entries(perType).map(([name, value]) => ({
    name,
    value,
    pct: totalValue > 0 ? (value / totalValue) * 100 : 0,
  }));

  /* ── render ────────────────────────────────────────────── */
  return (
    <div style={{ marginTop: "1rem" }}>
      <h2>{portfolio.name}</h2>

      {typeRows.length > 0 && (
        <div style={{ width: "100%", height: 240, margin: "1rem 0" }}>
          <ResponsiveContainer>
            <PieChart>
              <Pie
                dataKey="value"
                data={typeRows}
                label={({ name, pct }) => `${name} ${percent(pct)}`}
              >
                {typeRows.map((_, idx) => (
                  <Cell
                    key={`cell-${idx}`}
                    fill={PIE_COLORS[idx % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v: number, n: string) => [money(v), n]} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

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
      {portfolio.accounts?.map((acct, idx) => {
        const key = accountKey(acct, idx);
        const checked = activeKeys.has(key);
        return (
          <div key={key} style={{ marginBottom: "1.5rem" }}>
            <h3>
              <input
                type="checkbox"
                checked={checked}
                onChange={() =>
                  setSelectedAccounts((prev) =>
                    prev.includes(key)
                      ? prev.filter((k) => k !== key)
                      : [...prev, key]
                  )
                }
                aria-label={`${acct.owner ?? "—"} ${acct.account_type}`}
                style={{ marginRight: "0.5rem" }}
              />
              {acct.owner ?? "—"} • {acct.account_type} — {money(acct.value_estimate_gbp)}
            </h3>

            {checked && (
              <HoldingsTable
                holdings={acct.holdings ?? []}
                relativeView={relativeView}
                onSelectInstrument={(ticker, name) =>
                  setSelected({ ticker, name })
                }
              />
            )}
          </div>
        );
      })}

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
