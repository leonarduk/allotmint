import React, { useEffect } from "react";
import type { Holding } from "../types";

function eligibilityBadge(h: Holding) {
  if (h.sell_eligible === true) return <span style={{ color: "green" }}>✓ Eligible</span>;
  if (typeof h.days_until_eligible === "number")
    return <span style={{ color: "red" }}>{h.days_until_eligible}d to go</span>;
  return <span style={{ color: "gray" }}>Unknown</span>;
}

function fmtMoney(v?: number | null) {
  if (v == null) return "";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtGain(v?: number | null) {
  if (v == null) return "";
  const style: React.CSSProperties = { color: v >= 0 ? "green" : "red" };
  return <span style={style}>{fmtMoney(v)}</span>;
}

type Props = { holdings: Holding[] };

export function HoldingsTable({ holdings }: Props) {
  useEffect(() => {
    console.info("HoldingsTable mounted with data:", holdings);
  }, [holdings]);

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "1.5rem" }}>
      <thead>
        <tr>
          <th style={th}>Ticker</th>
          <th style={th}>Units</th>
          <th style={th}>Px £</th>
          <th style={th}>Cost £</th>
          <th style={th}>Mkt £</th>
          <th style={th}>Gain £</th>
          <th style={th}>Acquired</th>
          <th style={th}>Days Held</th>
          <th style={th}>Eligible?</th>
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => {
          console.info("Rendering row for:", h.ticker, h);
          return (
            <tr key={h.ticker} style={tr}>
              <td style={td}>{h.ticker}</td>
              <td style={td}>{h.units}</td>
              <td style={td}>{fmtMoney(h.current_price_gbp)}</td>
              <td style={td}>{fmtMoney(h.cost_basis_gbp)}</td>
              <td style={td}>{fmtMoney(h.market_value_gbp)}</td>
              <td style={td}>{fmtGain(h.gain_gbp)}</td>
              <td style={td}>{h.acquired_date ?? ""}</td>
              <td style={td}>{h.days_held ?? ""}</td>
              <td style={td}>{eligibilityBadge(h)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "1px solid #ccc",
  padding: "4px",
};
const td: React.CSSProperties = {
  padding: "4px",
  borderBottom: "1px solid #eee",
};
const tr: React.CSSProperties = {};
