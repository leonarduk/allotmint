import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
      .then((d) =>
        setData(d as { prices: Price[]; positions: Position[] })
      )
      .catch((e: Error) => setErr(e.message));
  }, [ticker]);

  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  const rawPrices = (data.prices ?? [])
    .map((p) => ({ date: p.date, close_gbp: toNum(p.close_gbp) }))
    .filter((p) => Number.isFinite(p.close_gbp));

  const prices = rawPrices.map((p, i) => {
    const prev = rawPrices[i - 1];
    const change_gbp = prev ? p.close_gbp - prev.close_gbp : NaN;
    const change_pct = prev ? (change_gbp / prev.close_gbp) * 100 : NaN;
    return { ...p, change_gbp, change_pct };
  });

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
                <Link
                  to={`/member/${encodeURIComponent(pos.owner)}`}
                  style={{ color: "#00d8ff", textDecoration: "none" }}
                >
                  {pos.owner} – {pos.account}
                </Link>
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
            <th align="right">Δ £</th>
            <th align="right">Δ %</th>
          </tr>
        </thead>
        <tbody>
          {prices
            .slice(-60)
            .reverse()
            .map((p) => {
              const colour = Number.isFinite(p.change_gbp)
                ? p.change_gbp >= 0
                  ? "lightgreen"
                  : "red"
                : undefined;
              return (
                <tr key={p.date}>
                  <td>{p.date}</td>
                  <td align="right">{fixed(p.close_gbp, 2)}</td>
                  <td align="right" style={{ color: colour }}>
                    {fixed(p.change_gbp, 2)}
                  </td>
                  <td align="right" style={{ color: colour }}>
                    {Number.isFinite(p.change_pct)
                      ? `${fixed(p.change_pct, 2)}%`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          {!prices.length && (
            <tr>
              <td colSpan={4} style={{ textAlign: "center", color: "#888" }}>
                No price data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
