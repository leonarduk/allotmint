import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getPerformance, getValueAtRisk } from "../api";
import type { PerformancePoint, ValueAtRiskPoint } from "../types";

type Props = {
  owner: string | null;
};

export function PerformanceDashboard({ owner }: Props) {
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [varData, setVarData] = useState<ValueAtRiskPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<number>(365);

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    setVarData([]);
    const reqDays = days === 0 ? 36500 : days;
    Promise.all([
      getPerformance(owner, reqDays),
      getValueAtRisk(owner, { days: reqDays, confidence: 95 }),
    ])
      .then(([perf, varSeries]) => {
        setData(perf);
        setVarData(varSeries);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [owner, days]);

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
          <YAxis tickFormatter={(v) => `${(v * 100).toFixed(2)}%`} />
          <Tooltip formatter={(v: number) => `${(v * 100).toFixed(2)}%`} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: "2rem" }}>Value at Risk (95%)</h2>
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
