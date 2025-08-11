import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTradingSignals } from "../api";
import type { TradingSignal } from "../types";

export function TradingAgent() {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getTradingSignals()
      .then(setSignals)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (!signals.length) return <p>No signals.</p>;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left", padding: "4px" }}>Ticker</th>
          <th style={{ textAlign: "left", padding: "4px" }}>Action</th>
          <th style={{ textAlign: "left", padding: "4px" }}>Reason</th>
        </tr>
      </thead>
      <tbody>
        {signals.map((s) => (
          <tr key={s.ticker}>
            <td style={{ padding: "4px" }}>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  navigate(`/instrument/${s.ticker}`);
                }}
              >
                {s.ticker}
              </a>
            </td>
            <td style={{ padding: "4px" }}>{s.action}</td>
            <td style={{ padding: "4px" }}>{s.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default TradingAgent;

