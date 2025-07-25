// src/components/HoldingsTable.tsx
import React from "react";
import type { Holding } from "../types";

type Props = {
  holdings: Holding[];
};

/**
 * Simple tabular view of a list of holdings.
 * • Renders nothing if the array is empty.
 * • Adds basic styling so the table shows up nicely on a dark background.
 */
export function HoldingsTable({ holdings }: Props) {
  if (!holdings.length) return null;

  const thStyle: React.CSSProperties = { textAlign: "left", padding: "4px 6px" };
  const tdStyle: React.CSSProperties = { padding: "4px 6px" };

  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        marginBottom: "1rem",
        fontSize: "0.9rem",
      }}
    >
      <thead>
        <tr>
          <th style={thStyle}>Ticker</th>
          <th style={thStyle}>Name</th>                {/* ← NEW column */}
          <th style={{ ...thStyle, textAlign: "right" }}>Units</th>
          <th style={{ ...thStyle, textAlign: "right" }}>Px £</th>
          <th style={{ ...thStyle, textAlign: "right" }}>Cost £</th>
          <th style={{ ...thStyle, textAlign: "right" }}>Mkt £</th>
          <th style={{ ...thStyle, textAlign: "right" }}>Gain £</th>
          <th style={thStyle}>Acquired</th>
          <th style={{ ...thStyle, textAlign: "right" }}>Days Held</th>
          <th style={{ ...thStyle, textAlign: "center" }}>Eligible?</th>
        </tr>
      </thead>

      <tbody>
        {holdings.map((h) => {
          const gain = (h.gain_gbp ?? h.market_value_gbp! - (h.cost_basis_gbp ?? 0));
          return (
            <tr key={h.ticker + h.acquired_date}>
              <td style={tdStyle}>{h.ticker}</td>
              <td style={tdStyle}>{h.name}</td>           {/* NEW cell */}
              <td style={{ ...tdStyle, textAlign: "right" }}>
                {h.units.toLocaleString()}
              </td>
              <td style={{ ...tdStyle, textAlign: "right" }}>
                {(h.current_price_gbp ?? 0).toFixed(2)}
              </td>
              <td style={{ ...tdStyle, textAlign: "right" }}>
                {(h.cost_basis_gbp ?? 0).toFixed(2)}
              </td>
              <td style={{ ...tdStyle, textAlign: "right" }}>
                {(h.market_value_gbp ?? 0).toFixed(2)}
              </td>
              <td
                style={{
                  ...tdStyle,
                  textAlign: "right",
                  color: gain >= 0 ? "lightgreen" : "red",
                }}
              >
                {gain.toFixed(2)}
              </td>
              <td style={tdStyle}>{h.acquired_date}</td>
              <td style={{ ...tdStyle, textAlign: "right" }}>
                {h.days_held ?? "—"}
              </td>
              <td
                style={{
                  ...tdStyle,
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
