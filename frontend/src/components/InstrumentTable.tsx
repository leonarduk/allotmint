import type {InstrumentSummary} from "../types";

type Props = { rows: InstrumentSummary[] };

export function InstrumentTable({ rows }: Props) {
  if (!rows.length) return null;

  const header = { padding: "4px 6px", textAlign: "left" } as const;
  const right  = { ...header, textAlign: "right" };

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "1rem" }}>
      <thead>
        <tr>
          <th style={header}>Ticker</th>
          <th style={header}>Name</th>
          <th style={right}>Units</th>
          <th style={right}>Mkt £</th>
          <th style={right}>Gain £</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.ticker}>
            <td style={header}>{r.ticker}</td>
            <td style={header}>{r.name}</td>
            <td style={right}>{r.units.toLocaleString()}</td>
            <td style={right}>{r.market_value_gbp.toFixed(2)}</td>
            <td style={{ ...right, color: r.gain_gbp >= 0 ? "lightgreen" : "red" }}>
              {r.gain_gbp.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
