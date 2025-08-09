import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import { InstrumentDetail } from "../components/InstrumentDetail";

export function Screener() {
  const [tickers, setTickers] = useState("");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [fcfMin, setFcfMin] = useState("");

  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const { sorted, handleSort } = useSortableTable(rows, "peg_ratio");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols = tickers
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (!symbols.length) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getScreener(symbols, {
        peg_max: pegMax ? parseFloat(pegMax) : undefined,
        pe_max: peMax ? parseFloat(peMax) : undefined,
        de_max: deMax ? parseFloat(deMax) : undefined,
        fcf_min: fcfMin ? parseFloat(fcfMin) : undefined,
      });
      setRows(data);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          Tickers
          <input
            aria-label="Tickers"
            type="text"
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
            placeholder="AAPL,MSFT,…"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          Max PEG
          <input
            aria-label="Max PEG"
            type="number"
            value={pegMax}
            onChange={(e) => setPegMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          Max P/E
          <input
            aria-label="Max P/E"
            type="number"
            value={peMax}
            onChange={(e) => setPeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          Max D/E
          <input
            aria-label="Max D/E"
            type="number"
            value={deMax}
            onChange={(e) => setDeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          Min FCF
          <input
            aria-label="Min FCF"
            type="number"
            value={fcfMin}
            onChange={(e) => setFcfMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <button type="submit" disabled={loading} style={{ marginLeft: "0.5rem" }}>
          {loading ? "Loading…" : "Run"}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {loading && <p>Loading…</p>}

      {rows.length > 0 && !loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th
                style={{ ...cell, cursor: "pointer" }}
                onClick={() => handleSort("ticker")}
              >
                Ticker
              </th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>PEG</th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>P/E</th>
              <th style={right} onClick={() => handleSort("de_ratio")}>D/E</th>
              <th style={right} onClick={() => handleSort("fcf")}>FCF</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => setSelected(r.ticker)}
                style={{ cursor: "pointer" }}
              >
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

      {selected && (
        <InstrumentDetail
          ticker={selected}
          name={rows.find((r) => r.ticker === selected)?.name ?? ""}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default Screener;

