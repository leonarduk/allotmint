// src/components/InstrumentTable.tsx
import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";

type Props = {
  rows: InstrumentSummary[];
  groupSlug: string;
};

export function InstrumentTable({ rows, groupSlug }: Props) {
  const [ticker, setTicker] = useState<string | null>(null);

  /* no data? – render a clear message instead of an empty table */
  if (!rows.length) {
    return <p>No instruments found for this group.</p>;
  }

  /* simple cell styles */
  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right" } as const;

  return (
    <>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          cursor: "pointer",
          marginBottom: "1rem",
        }}
      >
        <thead>
          <tr>
            <th style={cell}>Ticker</th>
            <th style={cell}>Name</th>
            <th style={right}>Units</th>
            <th style={right}>Mkt £</th>
            <th style={right}>Gain £</th>
            <th style={right}>Last £</th>
            <th style={right}>Last&nbsp;Date</th>
            <th style={right}>Δ 7 d %</th>
            <th style={right}>Δ 1 mo %</th>
          </tr>
        </thead>

        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker} onClick={() => setTicker(r.ticker)}>
              <td style={cell}>{r.ticker}</td>
              <td style={cell}>{r.name}</td>
              <td style={right}>{r.units.toLocaleString()}</td>
              <td style={right}>{r.market_value_gbp.toFixed(2)}</td>
              <td
                style={{
                  ...right,
                  color: r.gain_gbp >= 0 ? "lightgreen" : "red",
                }}
              >
                {r.gain_gbp.toFixed(2)}
              </td>
              <td style={right}>
                {r.last_price_gbp != null ? r.last_price_gbp.toFixed(2) : "—"}
              </td>
              <td style={right}>{r.last_price_date ?? "—"}</td>
              <td style={right}>
                {r.change_7d_pct == null ? "—" : r.change_7d_pct.toFixed(1)}
              </td>
              <td style={right}>
                {r.change_30d_pct == null ? "—" : r.change_30d_pct.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* slide-in price-history / positions panel */}
      {ticker && (
        <InstrumentDetail
          slug={groupSlug}
          ticker={ticker}
          onClose={() => setTicker(null)}
        />
      )}
    </>
  );
}
