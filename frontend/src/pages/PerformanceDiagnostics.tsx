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
import EmptyState from "../components/EmptyState";

const THRESHOLD = 0.1; // highlight drops worse than -10%

export default function PerformanceDiagnostics() {
  const { owner = "" } = useParams<{ owner: string }>();
  const [history, setHistory] = useState<PerformancePoint[]>([]);
  const [holdings, setHoldings] = useState<HoldingValue[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!owner) {
      setHistory([]);
      setHoldings([]);
      setSelected(null);
      setErr(null);
      return;
    }

    let cancelled = false;
    setErr(null);
    setHistory([]);
    setHoldings([]);
    setSelected(null);

    getPerformance(owner)
      .then((res) => {
        if (cancelled) return;
        setHistory(res.history);
      })
      .catch((e) => {
        if (cancelled) return;
        setHistory([]);
        setHoldings([]);
        setSelected(null);
        const message =
          navigator.onLine
            ? e instanceof Error
              ? e.message
              : String(e)
            : "You appear to be offline.";
        setErr(message);
      });

    return () => {
      cancelled = true;
    };
  }, [owner]);

  const handleClick = async (date: string) => {
    try {
      const res = await getPortfolioHoldings(owner, date);
      setHoldings(res.holdings);
      setSelected(date);
      setErr(null);
    } catch (e) {
      setHoldings([]);
      setSelected(null);
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div style={{ padding: "1rem" }}>
      <h1>Performance Diagnostics – {owner}</h1>
      {err ? (
        <div role="alert" aria-live="assertive" style={{ marginTop: "1rem" }}>
          <EmptyState message="We couldn't load performance diagnostics right now. Please try again later." />
          <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>Error details: {err}</p>
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
