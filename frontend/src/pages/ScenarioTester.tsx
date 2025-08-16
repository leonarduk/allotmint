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
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <input
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          style={{ marginRight: "0.5rem" }}
        />
        <input
          type="number"
          placeholder="% Change"
          value={pct}
          onChange={(e) => setPct(e.target.value)}
          style={{ marginRight: "0.5rem" }}
        />
        <button onClick={handleRun}>Apply</button>
      </div>
      {error && <div style={{ color: "red" }}>{error}</div>}
      {results && (
        <pre style={{ maxHeight: "400px", overflow: "auto" }}>
          {JSON.stringify(results, null, 2)}
        </pre>
      )}
    </div>
  );
}
