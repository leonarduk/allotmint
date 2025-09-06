import { useState } from "react";
import { getRebalance } from "../api";
import type { TradeSuggestion } from "../types";

export default function Rebalance() {
  const [actualInput, setActualInput] = useState(
    '{\n  "AAPL": 4000,\n  "MSFT": 3000,\n  "CASH": 3000\n}'
  );
  const [targetInput, setTargetInput] = useState(
    '{\n  "AAPL": 0.4,\n  "MSFT": 0.4,\n  "GOOG": 0.2\n}'
  );
  const [trades, setTrades] = useState<TradeSuggestion[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const actual = JSON.parse(actualInput) as Record<string, number>;
      const target = JSON.parse(targetInput) as Record<string, number>;
      const res = await getRebalance(actual, target);
      setTrades(res);
      setErr(null);
    } catch (e) {
      setTrades(null);
      setErr(String(e));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Rebalance Portfolio</h1>
      <form
        onSubmit={handleSubmit}
        className="mb-4 flex flex-col gap-4 md:flex-row"
      >
        <div className="flex-1">
          <label className="mb-1 block font-bold">Actual holdings (JSON)</label>
          <textarea
            className="w-full border p-2 font-mono"
            rows={8}
            value={actualInput}
            onChange={(e) => setActualInput(e.target.value)}
          />
        </div>
        <div className="flex-1">
          <label className="mb-1 block font-bold">Target allocation (JSON)</label>
          <textarea
            className="w-full border p-2 font-mono"
            rows={8}
            value={targetInput}
            onChange={(e) => setTargetInput(e.target.value)}
          />
        </div>
        <div className="self-end">
          <button type="submit" className="mt-2 rounded bg-blue-500 px-4 py-2 text-white">
            Rebalance
          </button>
        </div>
      </form>
      {err && <p className="text-red-600">{err}</p>}
      {trades && trades.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Action</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.ticker}>
                <td>{t.ticker}</td>
                <td
                  className={
                    t.action === "buy" ? "text-green-600" : "text-red-600"
                  }
                >
                  {t.action.toUpperCase()}
                </td>
                <td>{t.amount.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {trades && trades.length === 0 && <p>No trades required.</p>}
    </div>
  );
}
