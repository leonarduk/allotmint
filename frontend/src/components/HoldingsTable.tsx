import type React from "react";
import type { Holding } from "../types";
import { money } from "../lib/money";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";

type Props = {
  holdings: Holding[];
  total_value_estimate_gbp?: number;
  onSelectInstrument?: (ticker: string, name: string) => void;
};

export function HoldingsTable({ holdings, total_value_estimate_gbp, onSelectInstrument }: Props) {

  const rows = holdings.map((h) => {
    const cost =
      (h.cost_basis_gbp ?? 0) > 0
        ? h.cost_basis_gbp ?? 0
        : h.effective_cost_basis_gbp ?? 0;

    const market = h.market_value_gbp ?? 0;
    const gain =
      h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
        ? h.gain_gbp
        : market - cost;

    const gain_pct =
      h.gain_pct !== undefined && h.gain_pct !== null
        ? h.gain_pct
        : cost
          ? (gain / cost) * 100
          : 0;

    const weight_pct =
      h.weight_pct !== undefined && h.weight_pct !== null
        ? h.weight_pct
        : total_value_estimate_gbp
          ? ((h.market_value_gbp ?? 0) / total_value_estimate_gbp) * 100
          : undefined;

    return { ...h, cost, market, gain, gain_pct, weight_pct };
  });

  const { sorted, sortKey, asc, handleSort } = useSortableTable(rows, "ticker");

  if (!rows.length) return null;

  return (
    <table className={tableStyles.table} style={{ marginBottom: "1rem" }}>
      <thead>
        <tr>
          <th
            className={`${tableStyles.cell} ${tableStyles.clickable}`}
            onClick={() => handleSort("ticker")}
          >
            Ticker{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            className={`${tableStyles.cell} ${tableStyles.clickable}`}
            onClick={() => handleSort("name")}
          >
            Name{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={tableStyles.cell}>CCY</th>
          <th className={tableStyles.cell}>Type</th>
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>Units</th>
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>Px £</th>
          <th
            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
            onClick={() => handleSort("cost")}
          >
            Cost £{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>Mkt £</th>
          <th
            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
            onClick={() => handleSort("gain")}
          >
            Gain £{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
            onClick={() => handleSort("gain_pct")}
          >
            Gain %{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
            onClick={() => handleSort("weight_pct")}
          >
            Weight %{sortKey === "weight_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={tableStyles.cell}>Acquired</th>
          <th
            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
            onClick={() => handleSort("days_held")}
          >
            Days&nbsp;Held{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${tableStyles.cell} ${tableStyles.center}`}>Eligible?</th>
        </tr>
      </thead>

      <tbody>
        {sorted.map((h) => {
          const handleClick = () => {
            onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
          };

          return (
            <tr key={h.ticker + h.acquired_date}>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={handleClick}
                  style={{
                    color: "dodgerblue",
                    textDecoration: "underline",
                    background: "none",
                    border: "none",
                    padding: 0,
                    font: "inherit",
                    cursor: "pointer",
                  }}
                >
                  {h.ticker}
                </button>
              </td>
              <td className={tableStyles.cell}>{h.name}</td>
              <td className={tableStyles.cell}>{h.currency ?? "—"}</td>
              <td className={tableStyles.cell}>{h.instrument_type ?? "—"}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{h.units.toLocaleString()}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(h.current_price_gbp)}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                title={
                  (h.cost_basis_gbp ?? 0) > 0
                    ? "Actual purchase cost"
                    : "Inferred from price on acquisition date"
                }
              >
                {money(h.cost)}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(h.market)}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: h.gain >= 0 ? "lightgreen" : "red" }}
              >
                {money(h.gain)}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: h.gain_pct >= 0 ? "lightgreen" : "red" }}
              >
                {Number.isFinite(h.gain_pct) ? h.gain_pct.toFixed(1) : "—"}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {Number.isFinite(h.weight_pct) ? h.weight_pct.toFixed(1) : "—"}
              </td>
              <td className={tableStyles.cell}>{h.acquired_date}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{h.days_held ?? "—"}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.center}`}
                style={{ color: h.sell_eligible ? "lightgreen" : "gold" }}
              >
                {h.sell_eligible ? "✓ Eligible" : `✗ ${h.days_until_eligible ?? ""}`}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
