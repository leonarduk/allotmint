import type React from "react";
import type { Holding } from "../types";
import { money } from "../lib/money";
import { useSortableTable } from "../hooks/useSortableTable";

type Props = {
  holdings: Holding[];
  onSelectInstrument?: (ticker: string, name: string) => void;
};

export function HoldingsTable({ holdings, onSelectInstrument }: Props) {
  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right" } as const;

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

    return { ...h, cost, market, gain, gain_pct };
  });

  const { sorted, sortKey, asc, handleSort } = useSortableTable(rows, "ticker");

  if (!rows.length) return null;

  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        marginBottom: "1rem",
      }}
    >
      <thead>
        <tr>
          <th
            style={{ ...cell, cursor: "pointer" }}
            onClick={() => handleSort("ticker")}
          >
            Ticker{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            style={{ ...cell, cursor: "pointer" }}
            onClick={() => handleSort("name")}
          >
            Name{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th style={cell}>CCY</th>
          <th style={right}>Units</th>
          <th style={right}>Px £</th>
          <th
            style={{ ...right, cursor: "pointer" }}
            onClick={() => handleSort("cost")}
          >
            Cost £{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th style={right}>Mkt £</th>
          <th
            style={{ ...right, cursor: "pointer" }}
            onClick={() => handleSort("gain")}
          >
            Gain £{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            style={{ ...right, cursor: "pointer" }}
            onClick={() => handleSort("gain_pct")}
          >
            Gain %{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th style={cell}>Acquired</th>
          <th
            style={{ ...right, cursor: "pointer" }}
            onClick={() => handleSort("days_held")}
          >
            Days&nbsp;Held{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th style={{ ...cell, textAlign: "center" }}>Eligible?</th>
        </tr>
      </thead>

      <tbody>
        {sorted.map((h) => {
          const handleClick = () => {
            onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
          };

          return (
            <tr key={h.ticker + h.acquired_date}>
              <td style={cell}>
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
              <td style={cell}>{h.name}</td>
              <td style={cell}>{h.currency ?? "—"}</td>
              <td style={cell}>{h.instrument_type ?? "—"}</td>
              <td style={right}>{h.units.toLocaleString()}</td>
              <td style={right}>{money(h.current_price_gbp)}</td>
              <td
                style={right}
                title={
                  (h.cost_basis_gbp ?? 0) > 0
                    ? "Actual purchase cost"
                    : "Inferred from price on acquisition date"
                }
              >
                {money(h.cost)}
              </td>
              <td style={right}>{money(h.market)}</td>
              <td
                style={{
                  ...right,
                  color: h.gain >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(h.gain)}
              </td>
              <td
                style={{
                  ...right,
                  color: h.gain_pct >= 0 ? "lightgreen" : "red",
                }}
              >
                {Number.isFinite(h.gain_pct) ? h.gain_pct.toFixed(1) : "—"}
              </td>
              <td style={cell}>{h.acquired_date}</td>
              <td style={right}>{h.days_held ?? "—"}</td>
              <td
                style={{
                  ...cell,
                  textAlign: "center",
                  color: h.sell_eligible ? "lightgreen" : "gold",
                }}
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
