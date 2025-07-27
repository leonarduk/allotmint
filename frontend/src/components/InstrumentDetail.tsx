import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { getInstrumentDetail } from "../api";

type Props = {
  slug: string;          // group slug
  ticker: string;        // instrument clicked
  onClose: () => void;
};

export function InstrumentDetail({ slug, ticker, onClose }: Props) {
  const [data, setData] = useState<{ prices: any[]; positions: any[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getInstrumentDetail(slug, ticker)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [slug, ticker]);

  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  return (
    <div style={{
      position: "fixed",
      top: 0, right: 0, bottom: 0, width: "420px",
      background: "#111", color: "#eee", padding: "1rem",
      overflowY: "auto", boxShadow: "-4px 0 8px rgba(0,0,0,0.5)"
    }}>
      <button onClick={onClose} style={{ float: "right" }}>✕</button>
      <h2>{ticker}</h2>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.prices}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip />
          <Line type="monotone" dataKey="close_gbp" stroke="#00d8ff" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      {/* Table */}
      <table style={{ width: "100%", fontSize: "0.85rem", marginBottom: "1rem" }}>
        <thead><tr><th>Date</th><th align="right">£ Close</th></tr></thead>
        <tbody>
          {data.prices.slice(-60).reverse().map(p => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td align="right">{p.close_gbp.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Positions */}
      <h3>Positions</h3>
      <table style={{ width: "100%", fontSize: "0.85rem" }}>
        <thead>
          <tr>
            <th>Owner</th><th align="right">Units</th>
            <th align="right">Mkt £</th><th align="right">Gain £</th>
          </tr>
        </thead>
        <tbody>
          {data.positions.map(pos => (
            <tr key={pos.owner}>
              <td>{pos.owner}</td>
              <td align="right">{pos.units}</td>
              <td align="right">{pos.market_value_gbp.toFixed(2)}</td>
              <td
                align="right"
                style={{ color: pos.unrealised_gain_gbp >= 0 ? 'lightgreen' : 'red' }}
              >
                {pos.unrealised_gain_gbp.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
