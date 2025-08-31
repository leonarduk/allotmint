import { useState } from "react";
import { runScenario } from "../api";
import type { ScenarioResult } from "../types";

export default function ScenarioTester() {
  const [ticker, setTicker] = useState("");
  const [pct, setPct] = useState("");
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setError(null);
    try {
      const pctNum = parseFloat(pct);
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
        <button onClick={handleRun}>Apply</button>
      </div>
      {error && <div className="text-red-500">{error}</div>}
      {results && (
        <pre className="max-h-96 overflow-auto">
          {JSON.stringify(results, null, 2)}
        </pre>
      )}
    </div>
  );
}
