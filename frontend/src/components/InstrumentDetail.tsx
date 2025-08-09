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
import { money, percent } from "../lib/money";
import tableStyles from "../styles/table.module.css";

type Props = {
  ticker: string;
  name: string;
  currency?: string;
  instrument_type?: string | null;
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
  gain_pct?: number | null | undefined;
};

// ───────────────── helpers ─────────────────
const toNum = (v: unknown): number =>
  typeof v === "number" && Number.isFinite(v) ? v : NaN;

const fixed = (v: unknown, dp = 2): string => {
  const n = toNum(v);
  return Number.isFinite(n) ? n.toFixed(dp) : "—";
};

export function InstrumentDetail({
  ticker,
  name,
  currency: currencyProp,
  instrument_type,
  onClose,
}: Props) {
  const [data, setData] = useState<{
    prices: Price[];
    positions: Position[];
    currency?: string | null;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [currency, setCurrency] = useState<string | null>(currencyProp ?? null);
  const [showBollinger, setShowBollinger] = useState(false);
  const [days, setDays] = useState<number>(365);

  useEffect(() => {
    getInstrumentDetail(ticker, days)
      .then((d) => {
        const detail = d as {
          prices: Price[];
          positions: Position[];
          currency?: string | null;
        };
        setData(detail);
        setCurrency(detail.currency ?? currencyProp ?? null);
      })
      .catch((e: Error) => setErr(e.message));
  }, [ticker, days, currencyProp]);

  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  const rawPrices = (data.prices ?? [])
    .map((p) => ({ date: p.date, close_gbp: toNum(p.close_gbp) }))
    .filter((p) => Number.isFinite(p.close_gbp));

  const withChanges = rawPrices.map((p, i) => {
    const prev = rawPrices[i - 1];
    const change_gbp = prev ? p.close_gbp - prev.close_gbp : NaN;
    const change_pct = prev ? (change_gbp / prev.close_gbp) * 100 : NaN;
    return { ...p, change_gbp, change_pct };
  });

  const prices = withChanges.map((p, i, arr) => {
    const start = Math.max(0, i - 19);
    const slice = arr.slice(start, i + 1);
    const mean =
      slice.reduce((sum, s) => sum + s.close_gbp, 0) / slice.length;
    const variance =
      slice.reduce((sum, s) => sum + Math.pow(s.close_gbp - mean, 2), 0) /
      slice.length;
    const stdDev = Math.sqrt(variance);
    const hasFullWindow = slice.length === 20;
    return {
      ...p,
      bb_mid: hasFullWindow ? mean : NaN,
      bb_upper: hasFullWindow ? mean + 2 * stdDev : NaN,
      bb_lower: hasFullWindow ? mean - 2 * stdDev : NaN,
    };
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
      <div style={{ fontSize: "0.85rem", color: "#aaa", marginBottom: "1rem" }}>
        {ticker} • {currency ?? "?"} • {instrument_type ?? "?"}
      </div>

      {/* Chart */}
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ fontSize: "0.85rem", marginRight: "1rem" }}>
          Range:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ marginLeft: "0.25rem" }}
          >
            <option value={7}>1W</option>
            <option value={30}>1M</option>
            <option value={365}>1Y</option>
            <option value={3650}>10Y</option>
            <option value={0}>MAX</option>
          </select>
        </label>
        <label style={{ fontSize: "0.85rem" }}>
          <input
            type="checkbox"
            checked={showBollinger}
            onChange={(e) => setShowBollinger(e.target.checked)}
          />
          {" "}Bollinger Bands
        </label>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={prices}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip />
          {showBollinger && (
            <>
              <Line
                type="monotone"
                dataKey="bb_upper"
                stroke="#8884d8"
                dot={false}
                strokeDasharray="3 3"
              />
              <Line
                type="monotone"
                dataKey="bb_mid"
                stroke="#ff7300"
                dot={false}
                strokeDasharray="5 5"
              />
              <Line
                type="monotone"
                dataKey="bb_lower"
                stroke="#8884d8"
                dot={false}
                strokeDasharray="3 3"
              />
            </>
          )}
          <Line type="monotone" dataKey="close_gbp" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      {/* Positions */}
      <h3 style={{ marginTop: "1.5rem" }}>Positions</h3>
      <table className={tableStyles.table} style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Account</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Units</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Mkt £</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Gain £</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Gain %</th>
          </tr>
        </thead>
        <tbody>
          {(positions ?? []).map((pos, i) => (
            <tr key={`${pos.owner}-${pos.account}-${i}`}>
              <td className={tableStyles.cell}>
                <Link
                  to={`/member/${encodeURIComponent(pos.owner)}`}
                  style={{ color: "#00d8ff", textDecoration: "none" }}
                >
                  {pos.owner} – {pos.account}
                </Link>
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{fixed(pos.units, 4)}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(pos.market_value_gbp)}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{
                  color:
                    toNum(pos.unrealised_gain_gbp) >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(pos.unrealised_gain_gbp)}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{
                  color: toNum(pos.gain_pct) >= 0 ? "lightgreen" : "red",
                }}
              >
                {percent(pos.gain_pct, 1)}
              </td>
            </tr>
          ))}
          {!positions.length && (
            <tr>
              <td
                colSpan={4}
                className={`${tableStyles.cell} ${tableStyles.center}`}
                style={{ color: "#888" }}
              >
                No positions
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Recent Prices */}
      <h3>Recent Prices</h3>
      <table className={tableStyles.table} style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Date</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>£ Close</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ £</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ %</th>
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
                  <td className={tableStyles.cell}>{p.date}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>{fixed(p.close_gbp, 2)}</td>
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right}`}
                    style={{ color: colour }}
                  >
                    {fixed(p.change_gbp, 2)}
                  </td>
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right}`}
                    style={{ color: colour }}
                  >
                    {percent(p.change_pct, 2)}
                  </td>
                </tr>
              );
            })}
          {!prices.length && (
            <tr>
              <td
                colSpan={4}
                className={`${tableStyles.cell} ${tableStyles.center}`}
                style={{ color: "#888" }}
              >
                No price data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
