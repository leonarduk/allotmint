import { useState } from "react";
import { runScenario } from "../api";
import type { ScenarioResult } from "../types";

export default function ScenarioTester() {
  const [ticker, setTicker] = useState("");
  const [pct, setPct] = useState("");
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pctNum = parseFloat(pct);
  const canRun = ticker.trim() !== "" && !isNaN(pctNum);
  const fmt = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  });

  async function handleRun() {
    setError(null);
    try {
      const data = await runScenario(ticker, pctNum);
      setResults(data);
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <div className="mb-4 flex flex-col gap-2 md:flex-row">
        <input
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          className="md:mr-2"
        />
        <input
          type="number"
          placeholder="% Change"
          value={pct}
          onChange={(e) => setPct(e.target.value)}
          className="md:mr-2"
        />
        <button onClick={handleRun} disabled={!canRun}>
          Apply
        </button>
      </div>
      {error && <div className="text-red-500">{error}</div>}
      {results && (
        <div className="overflow-auto">
          <table className="min-w-full border">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-2 text-left">Owner</th>
                <th className="p-2 text-right">Baseline (£)</th>
                <th className="p-2 text-right">Shocked (£)</th>
                <th className="p-2 text-right">Delta (£)</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2">{r.owner}</td>
                  <td className="p-2 text-right">
                    {r.baseline_total_value_gbp != null
                      ? fmt.format(r.baseline_total_value_gbp)
                      : "—"}
                  </td>
                  <td className="p-2 text-right">
                    {r.shocked_total_value_gbp != null
                      ? fmt.format(r.shocked_total_value_gbp)
                      : "—"}
                  </td>
                  <td className="p-2 text-right">
                    {r.delta_gbp != null ? fmt.format(r.delta_gbp) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
