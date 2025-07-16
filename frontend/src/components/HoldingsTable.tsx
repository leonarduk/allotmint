import React from "react";
import type { Holding } from "../types";

function eligibilityBadge(h: Holding) {
  if (h.sell_eligible) return <span style={{ color: "green" }}>✓ Eligible</span>;
  if (h.days_until_eligible != null)
    return <span style={{ color: "red" }}>{h.days_until_eligible}d to go</span>;
  return <span style={{ color: "gray" }}>Unknown</span>;
}

type Props = { holdings: Holding[]; };

export function HoldingsTable({ holdings }: Props) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "1.5rem" }}>
      <thead>
        <tr>
          <th style={th}>Ticker</th>
          <th style={th}>Units</th>
          <th style={th}>Cost £</th>
          <th style={th}>Acquired</th>
          <th style={th}>Days Held</th>
          <th style={th}>Eligible?</th>
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => (
          <tr key={h.ticker} style={tr}>
            <td style={td}>{h.ticker}</td>
            <td style={td}>{h.units}</td>
            <td style={td}>{h.cost_basis_gbp?.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}</td>
            <td style={td}>{h.acquired_date ?? ""}</td>
            <td style={td}>{h.days_held ?? ""}</td>
            <td style={td}>{eligibilityBadge(h)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const th: React.CSSProperties = { textAlign: "left", borderBottom: "1px solid #ccc", padding: "4px" };
const td: React.CSSProperties = { padding: "4px", borderBottom: "1px solid #eee" };
const tr: React.CSSProperties = {};