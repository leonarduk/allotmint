import { useState } from "react";
import type { Holding } from "../types";
import { money } from "../lib/money";

type SortKey = "ticker" | "name" | "cost" | "gain" | "days_held";

type Props = {
  holdings: Holding[];
  onSelectInstrument?: (ticker: string, name: string) => void;
};

export function HoldingsTable({ holdings, onSelectInstrument }: Props) {
  if (!holdings.length) return null;

  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [asc, setAsc] = useState(true);

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right" } as const;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setAsc(!asc);
    } else {
      setSortKey(key);
      setAsc(true);
    }
  }

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

    return { ...h, cost, market, gain };
  });

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey as keyof typeof a];
    const vb = b[sortKey as keyof typeof b];
    if (typeof va === "string" && typeof vb === "string") {
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    const na = (va as number) ?? 0;
    const nb = (vb as number) ?? 0;
    return asc ? na - nb : nb - na;
  });

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
          <th style={cell}>Ticker</th>
          <th style={cell}>Name</th>
          <th style={cell}>CCY</th>
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
          const handleClick = (e: React.MouseEvent) => {
            e.preventDefault();
            onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
          };

          return (
            <tr key={h.ticker + h.acquired_date}>
              <td style={cell}>
                <a
                  href="#"
                  onClick={handleClick}
                  style={{ color: "dodgerblue", textDecoration: "underline" }}
                >
                  {h.ticker}
                </a>
              </td>
              <td style={cell}>{h.name}</td>
              <td style={cell}>{h.currency ?? "—"}</td>
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
