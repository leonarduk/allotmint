// src/components/InstrumentTable.tsx
// src/components/InstrumentTable.tsx
import type {InstrumentSummary} from "../types";

type Props = { rows: InstrumentSummary[] };

const hd = { padding: "4px 6px", textAlign: "left" } as const;
const rt = { ...hd, textAlign: "right" };

export function InstrumentTable({ rows }: Props) {
  if (!rows.length) return null;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "1rem" }}>
      <thead>
        <tr>
          <th style={hd}>Ticker</th>
          <th style={hd}>Name</th>
          <th style={rt}>Units</th>
          <th style={rt}>Mkt £</th>
          <th style={rt}>Gain £</th>
          <th style={rt}>Last £</th>
          <th style={rt}>Last&nbsp;Date</th>
          <th style={rt}>Δ 7 d %</th>
          <th style={rt}>Δ 1 mo %</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.ticker}>
            <td style={hd}>{r.ticker}</td>
            <td style={hd}>{r.name}</td>
            <td style={rt}>{r.units.toLocaleString()}</td>
            <td style={rt}>{r.market_value_gbp.toFixed(2)}</td>
            <td style={{ ...rt, color: r.gain_gbp >= 0 ? "lightgreen" : "red" }}>
              {r.gain_gbp.toFixed(2)}
            </td>
            <td style={rt}>{r.last_price_gbp?.toFixed(2) ?? "—"}</td>
            <td style={rt}>{r.last_price_date ?? "—"}</td>
            <td style={rt}>
              {r.change_7d_pct == null ? "—" : r.change_7d_pct.toFixed(1)}
            </td>
            <td style={rt}>
              {r.change_30d_pct == null ? "—" : r.change_30d_pct.toFixed(1)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
