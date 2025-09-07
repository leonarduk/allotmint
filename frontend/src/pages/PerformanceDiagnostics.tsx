import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getPerformance, getPortfolioHoldings } from "../api";
import type { PerformancePoint, HoldingValue } from "../types";
import { percent } from "../lib/money";

const THRESHOLD = 0.1; // highlight drops worse than -10%

export default function PerformanceDiagnostics() {
  const { owner = "" } = useParams<{ owner: string }>();
  const [history, setHistory] = useState<PerformancePoint[]>([]);
  const [holdings, setHoldings] = useState<HoldingValue[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!owner) return;
    getPerformance(owner).then((res) => setHistory(res.history));
  }, [owner]);

  const handleClick = async (date: string) => {
    try {
      const res = await getPortfolioHoldings(owner, date);
      setHoldings(res.holdings);
      setSelected(date);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div style={{ padding: "1rem" }}>
      <h1>Performance Diagnostics – {owner}</h1>
      {err && <p style={{ color: "red" }}>{err}</p>}
      <ResponsiveContainer width="100%" height={240}>
        <LineChart
          data={history}
          onClick={(e) => {
            if (e && (e as any).activeLabel) handleClick((e as any).activeLabel);
          }}
        >
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100)} />
          <Tooltip formatter={(v: number) => percent(v * 100)} />
          <Line
            type="monotone"
            dataKey="drawdown"
            stroke="#8884d8"
            dot={({ cx, cy, payload }) => (
              <circle
                cx={cx}
                cy={cy}
                r={payload.drawdown < -THRESHOLD ? 4 : 2}
                fill={payload.drawdown < -THRESHOLD ? "red" : "#8884d8"}
              />
            )}
          />
        </LineChart>
      </ResponsiveContainer>
      {selected && holdings.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <h2>Holdings on {selected}</h2>
          <ul>
            {holdings.map((h) => (
              <li key={`${h.ticker}.${h.exchange}`}>
                <a
                  href={`/timeseries?ticker=${encodeURIComponent(
                    h.ticker,
                  )}&exchange=${encodeURIComponent(h.exchange)}`}
                >
                  {h.ticker}.{h.exchange}
                </a>
                : {h.units} @ {h.price ?? "n/a"} = {h.value ?? "n/a"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
