/* ---------------------------------------------------------------------------
   InstrumentDetail.tsx – side-panel price/position viewer
   --------------------------------------------------------------------------- */

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { getInstrumentDetail } from "../api";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
interface PricePoint {
  date: string;         // "YYYY-MM-DD"
  close_gbp: number;    // guaranteed finite
}

interface PositionRow {
  owner: string;
  units: number;
  market_value_gbp: number;
  unrealised_gain_gbp: number;
}

interface Props {
  ticker: string;       // e.g. "XDEV.L"
  onClose: () => void;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export function InstrumentDetail({ ticker, onClose }: Props) {
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  /* ── fetch on mount / ticker-change ─────────────────────────────── */
  useEffect(() => {
    setLoading(true);
    setErr(null);

    getInstrumentDetail(ticker)
      .then((res: any) => {
        /* keep only rows with a proper finite price */
        const clean: PricePoint[] = (res.prices as PricePoint[])
          .filter((p) => Number.isFinite(p.close_gbp))
          .sort((a, b) => a.date.localeCompare(b.date));

        setPrices(clean);
        setPositions(res.positions as PositionRow[]);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  /* ── render ─────────────────────────────────────────────────────── */
  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (loading) return <p>Loading…</p>;
  if (!prices.length)
    return <p style={{ fontStyle: "italic" }}>No price data available.</p>;

  return (
    <aside
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
      <h2 style={{ marginTop: 0 }}>{ticker}</h2>

      {/* ── chart ─────────────────────────────────────────────── */}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={prices}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip
            formatter={(v: number) =>
              `£${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
            }
          />
          <Line
            type="monotone"
            dataKey="close_gbp"
            stroke="#00d8ff"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>

      {/* ── recent closing prices ─────────────────────────────── */}
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
                <td align="right">{p.close_gbp.toFixed(2)}</td>
              </tr>
            ))}
        </tbody>
      </table>

      {/* ── positions ─────────────────────────────────────────── */}
      <h3 style={{ marginTop: "1rem" }}>Positions</h3>
      <table style={{ width: "100%", fontSize: "0.85rem" }}>
        <thead>
          <tr>
            <th>Owner</th>
            <th align="right">Units</th>
            <th align="right">Mkt £</th>
            <th align="right">Gain £</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr key={`${pos.owner}-${pos.units}`}>
              <td>{pos.owner}</td>
              <td align="right">{pos.units}</td>
              <td align="right">{pos.market_value_gbp.toFixed(2)}</td>
              <td
                align="right"
                style={{
                  color:
                    pos.unrealised_gain_gbp >= 0 ? "lightgreen" : "salmon",
                }}
              >
                {pos.unrealised_gain_gbp.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  );
}
