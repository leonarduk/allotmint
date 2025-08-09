import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getPerformance } from "../api";
import type { PerformancePoint } from "../types";

type Props = {
  owner: string | null;
};

export function PerformanceDashboard({ owner }: Props) {
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    getPerformance(owner)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [owner]);

  if (!owner) return <p>Select a member.</p>;
  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data.length) return <p>Loading…</p>;

  return (
    <div style={{ marginTop: "1rem" }}>
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
    </div>
  );
}

export default PerformanceDashboard;
