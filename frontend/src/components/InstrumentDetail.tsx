import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getInstrumentDetail } from "../api";

type Props = {
  ticker: string;
  name: string;
  onClose: () => void;
};

type Price = {
  date: string;
  close_gbp: number | null | undefined;
};

type Position = {
  owner: string;
  account: string;
  units: number | null | undefined;
  market_value_gbp: number | null | undefined;
  unrealised_gain_gbp: number | null | undefined;
};

// ───────────────── helpers ─────────────────
const toNum = (v: unknown): number =>
  typeof v === "number" && Number.isFinite(v) ? v : NaN;

const fixed = (v: unknown, dp = 2): string => {
  const n = toNum(v);
  return Number.isFinite(n) ? n.toFixed(dp) : "—";
};

const money = (v: unknown): string => {
  const n = toNum(v);
  return Number.isFinite(n)
    ? `£${n.toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`
    : "—";
};

export function InstrumentDetail({ ticker, name, onClose }: Props) {
  const [data, setData] = useState<{ prices: Price[]; positions: Position[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getInstrumentDetail(ticker)
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, [ticker]);

  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  const prices = (data.prices ?? [])
    .map((p) => ({ date: p.date, close_gbp: toNum(p.close_gbp) }))
    .filter((p) => Number.isFinite(p.close_gbp));

  const positions = data.positions ?? [];

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: "420px",
        background: "#111",
        color: "#eee",
        padding: "1rem",
        overflowY: "auto",
        boxShadow: "-4px 0 8px rgba(0,0,0,0.5)",
      }}
    >
      <button onClick={onClose} style={{ float: "right" }}>
        ✕
      </button>
      <h2 style={{ marginBottom: "0.2rem" }}>{name}</h2>
      <div style={{ fontSize: "0.85rem", color: "#aaa", marginBottom: "1rem" }}>{ticker}</div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={prices}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip />
          <Line type="monotone" dataKey="close_gbp" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      {/* Positions */}
      <h3 style={{ marginTop: "1.5rem" }}>Positions</h3>
      <table
        style={{
          width: "100%",
          fontSize: "0.85rem",
          marginBottom: "1rem",
        }}
      >
        <thead>
          <tr>
            <th>Account</th>
            <th align="right">Units</th>
            <th align="right">Mkt £</th>
            <th align="right">Gain £</th>
          </tr>
        </thead>
        <tbody>
          {(positions ?? []).map((pos, i) => (
            <tr key={`${pos.owner}-${pos.account}-${i}`}>
              <td>
                <a
                  href={`/member/${encodeURIComponent(pos.owner)}`}
                  style={{ color: "#00d8ff", textDecoration: "none" }}
                >
                  {pos.owner} – {pos.account}
                </a>
              </td>
              <td align="right">{fixed(pos.units, 4)}</td>
              <td align="right">{money(pos.market_value_gbp)}</td>
              <td
                align="right"
                style={{
                  color:
                    toNum(pos.unrealised_gain_gbp) >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(pos.unrealised_gain_gbp)}
              </td>
            </tr>
          ))}
          {!positions.length && (
            <tr>
              <td colSpan={4} style={{ textAlign: "center", color: "#888" }}>
                No positions
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Recent Prices */}
      <h3>Recent Prices</h3>
      <table
        style={{
          width: "100%",
          fontSize: "0.85rem",
          marginBottom: "1rem",
        }}
      >
        <thead>
          <tr>
            <th>Date</th>
            <th align="right">£ Close</th>
          </tr>
        </thead>
        <tbody>
          {prices
            .slice(-60)
            .reverse()
            .map((p) => (
              <tr key={p.date}>
                <td>{p.date}</td>
                <td align="right">{fixed(p.close_gbp, 2)}</td>
              </tr>
            ))}
          {!prices.length && (
            <tr>
              <td colSpan={2} style={{ textAlign: "center", color: "#888" }}>
                No price data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
