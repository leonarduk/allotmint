import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getPerformance,
  getValueAtRisk,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
} from "../api";
import type { PerformancePoint, ValueAtRiskPoint } from "../types";
import { percent } from "../lib/money";
import i18n from "../i18n";

type Props = {
  owner: string | null;
};

export function PerformanceDashboard({ owner }: Props) {
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [varData, setVarData] = useState<ValueAtRiskPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<number>(365);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null);
  const [excludeCash, setExcludeCash] = useState<boolean>(false);

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    setVarData([]);
    const reqDays = days === 0 ? 36500 : days;
    Promise.all([
      getAlphaVsBenchmark(owner, "VWRL.L", reqDays),
      getTrackingError(owner, "VWRL.L", reqDays),
      getMaxDrawdown(owner, reqDays),
      getPerformance(owner, reqDays, excludeCash),
      getValueAtRisk(owner, {
        days: reqDays,
        confidence: 95,
        excludeCash,
      }),
    ])
      .then(([alphaRes, teRes, mdRes, perf, varSeries]) => {
        setData(perf);
        setVarData(varSeries);
        setAlpha(alphaRes.alpha_vs_benchmark);
        setTrackingError(teRes.tracking_error);
        setMaxDrawdown(mdRes.max_drawdown);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [owner, days, excludeCash]);

  if (!owner) return <p>Select a member.</p>;
  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data.length) return <p>Loading…</p>;

  return (
    <div style={{ marginTop: "1rem" }}>
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ fontSize: "0.85rem" }}>
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
        <label style={{ fontSize: "0.85rem", marginLeft: "1rem" }}>
          Exclude cash
          <input
            type="checkbox"
            checked={excludeCash}
            onChange={(e) => setExcludeCash(e.target.checked)}
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
      </div>
      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1rem",
        }}
      >
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Alpha vs Benchmark</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percent(alpha != null ? alpha * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Tracking Error</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percent(trackingError != null ? trackingError * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>Max Drawdown</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percent(maxDrawdown != null ? maxDrawdown * 100 : null)}
          </div>
        </div>
      </div>
      <h2>Portfolio Value</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: "2rem" }}>Cumulative Return</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100, 2, i18n.language)} />
          <Tooltip formatter={(v: number) => percent(v * 100, 2, i18n.language)} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: "2rem" }}>Value at Risk (95%)</h2>
      <p style={{ fontSize: "0.85rem", marginTop: "-0.5rem" }}>
        <a href="/docs/value_at_risk.md" target="_blank" rel="noopener noreferrer">
          Methodology
        </a>
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={varData}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="var" stroke="#ff7300" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PerformanceDashboard;
