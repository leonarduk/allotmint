import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";

export function ScreenerPage() {
  const [tickers, setTickers] = useState("");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [fcfMin, setFcfMin] = useState("");

  const [results, setResults] = useState<ScreenerResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols = tickers
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    if (!symbols.length) {
      setError("Please enter at least one ticker");
      return;
    }
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const res = await getScreener({
        tickers: symbols,
        peg_max: pegMax ? Number(pegMax) : undefined,
        pe_max: peMax ? Number(peMax) : undefined,
        de_max: deMax ? Number(deMax) : undefined,
        fcf_min: fcfMin ? Number(fcfMin) : undefined,
      });
      setResults(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const { sorted, handleSort } = useSortableTable(results ?? [], "peg_ratio");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <div style={{ marginBottom: "0.5rem" }}>
          <label>
            Tickers:
            <input
              type="text"
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="AAPL,MSFT"
              style={{ marginLeft: "0.5rem" }}
            />
          </label>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <label>
            PEG ≤
            <input
              type="number"
              value={pegMax}
              onChange={(e) => setPegMax(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem", width: "5rem" }}
            />
          </label>
          <label>
            P/E ≤
            <input
              type="number"
              value={peMax}
              onChange={(e) => setPeMax(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem", width: "5rem" }}
            />
          </label>
          <label>
            D/E ≤
            <input
              type="number"
              value={deMax}
              onChange={(e) => setDeMax(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem", width: "5rem" }}
            />
          </label>
          <label>
            FCF ≥
            <input
              type="number"
              value={fcfMin}
              onChange={(e) => setFcfMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem", width: "5rem" }}
            />
          </label>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Loading…" : "Run"}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {!loading && results && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...cell, cursor: "pointer" }} onClick={() => handleSort("ticker")}>Ticker</th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>PEG</th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>P/E</th>
              <th style={right} onClick={() => handleSort("de_ratio")}>D/E</th>
              <th style={right} onClick={() => handleSort("fcf")}>FCF</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.ticker}>
                <td style={cell}>{r.ticker}</td>
                <td style={right}>{r.peg_ratio ?? "—"}</td>
                <td style={right}>{r.pe_ratio ?? "—"}</td>
                <td style={right}>{r.de_ratio ?? "—"}</td>
                <td style={right}>{r.fcf != null ? r.fcf.toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default ScreenerPage;
