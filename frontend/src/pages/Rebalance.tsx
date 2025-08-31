import { useEffect, useState } from "react";
import { getRebalance } from "../api";
import type { TradeSuggestion } from "../types";

// Example actual holdings (market values) and target weights
const ACTUAL: Record<string, number> = {
  AAPL: 4000,
  MSFT: 3000,
  CASH: 3000,
};

const TARGET: Record<string, number> = {
  AAPL: 0.4,
  MSFT: 0.4,
  GOOG: 0.2,
};

export default function Rebalance() {
  const [trades, setTrades] = useState<TradeSuggestion[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});

  useEffect(() => {
    getRebalance(ACTUAL, TARGET)
      .then(setTrades)
      .catch((e) => setErr(String(e)));
  }, []);

  function decide(ticker: string, action: "accepted" | "ignored") {
    setDecisions((prev) => ({ ...prev, [ticker]: action }));
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Rebalance Suggestions</h1>
      {err && <p className="text-red-500">{err}</p>}
      {!err && trades.length === 0 && <p>No suggestions.</p>}
      {trades.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Action</th>
              <th>Amount</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.ticker}>
                <td>{t.ticker}</td>
                <td>{t.action}</td>
                <td>{t.amount.toFixed(2)}</td>
                <td>
                  {decisions[t.ticker] ? (
                    <span>{decisions[t.ticker]}</span>
                  ) : (
                    <>
                      <button
                        onClick={() => decide(t.ticker, "accepted")}
                        style={{ marginRight: "0.5rem" }}
                      >
                        Accept
                      </button>
                      <button onClick={() => decide(t.ticker, "ignored")}>
                        Ignore
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
