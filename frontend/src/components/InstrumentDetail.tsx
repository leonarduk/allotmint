import {useEffect, useState} from "react";
import {
  Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {getInstrumentDetail} from "../api";

type Props = {
  slug: string;      // still useful if you want to show it, but not needed here
  ticker: string;
  onClose: () => void;
};

export function InstrumentDetail({ticker, onClose}: Props) {
  const [data, setData] = useState<{ prices: any[]; positions: any[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    // new signature: (ticker: string, days = 365)
    getInstrumentDetail(ticker, 365)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [ticker]);        // slug no longer matters for this request

  if (err)  return <p style={{color: "red"}}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  return (
    <div
      style={{
        position: "fixed",
        top: 0, right: 0, bottom: 0, width: 420,
        background: "#111", color: "#eee", padding: "1rem",
        overflowY: "auto", boxShadow: "-4px 0 8px rgba(0,0,0,.5)",
      }}
    >
      <button onClick={onClose} style={{float: "right"}}>✕</button>
      <h2>{ticker}</h2>

      {/* ─── Price chart ─────────────────────────────────────── */}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.prices}>
          <XAxis dataKey="Date" hide />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip />
          {/* the backend returns “Close”, not close_gbp – tweak if needed */}
          <Line type="monotone" dataKey="Close" stroke="#00d8ff" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      {/* ─── Last 60 closes ─────────────────────────────────── */}
      <table style={{width: "100%", fontSize: ".85rem", marginBottom: "1rem"}}>
        <thead>
          <tr><th>Date</th><th style={{textAlign: "right"}}>£ Close</th></tr>
        </thead>
        <tbody>
          {data.prices.slice(-60).reverse().map(p => (
            <tr key={p.Date}>
              <td>{p.Date}</td>
              <td style={{textAlign: "right"}}>{(+p.Close).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ─── Positions ──────────────────────────────────────── */}
      <h3>Positions</h3>
      <table style={{width: "100%", fontSize: ".85rem"}}>
        <thead>
          <tr>
            <th>Owner</th>
            <th style={{textAlign: "right"}}>Units</th>
            <th style={{textAlign: "right"}}>Mkt £</th>
            <th style={{textAlign: "right"}}>Gain £</th>
          </tr>
        </thead>
        <tbody>
          {data.positions.map(pos => (
            <tr key={pos.owner}>
              <td>{pos.owner}</td>
              <td style={{textAlign: "right"}}>{pos.units}</td>
              <td style={{textAlign: "right"}}>{(pos.market_value_gbp ?? 0).toFixed(2)}</td>
              <td
                style={{
                  textAlign: "right",
                  color: (pos.unrealised_gain_gbp ?? 0) >= 0 ? "lightgreen" : "red",
                }}
              >
                {(pos.unrealised_gain_gbp ?? 0).toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
