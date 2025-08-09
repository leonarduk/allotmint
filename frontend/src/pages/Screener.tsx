import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";


type SortKey = "ticker" | "peg_ratio" | "pe_ratio" | "de_ratio" | "fcf";

export default function Screener() {
  const [tickers, setTickers] = useState("AAPL, MSFT, GOOG, AMZN, TSLA");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [fcfMin, setFcfMin] = useState("");

  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("peg_ratio");
  const [asc, setAsc] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols = tickers
      .split(/[\s,]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    if (!symbols.length) return;
    setLoading(true);
    setError(null);
    try {
      const criteria = {
        peg_max: pegMax ? Number(pegMax) : undefined,
        pe_max: peMax ? Number(peMax) : undefined,
        de_max: deMax ? Number(deMax) : undefined,
        fcf_min: fcfMin ? Number(fcfMin) : undefined,
      };
      const res = await getScreener(symbols, criteria);
      setRows(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setAsc(!asc);
    } else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey];
    const vb = b[sortKey];
    if (typeof va === "string" && typeof vb === "string") {
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    const na = (va as number) ?? 0;
    const nb = (vb as number) ?? 0;
    return asc ? na - nb : nb - na;
  });

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <div style={{ marginBottom: "0.5rem" }}>
          <label>
            Tickers
            <textarea
              rows={2}
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <label>
            PEG max
            <input
              type="number"
              value={pegMax}
              onChange={(e) => setPegMax(e.target.value)}
              style={{ width: "5rem", marginLeft: "0.25rem" }}
            />
          </label>
          <label>
            P/E max
            <input
              type="number"
              value={peMax}
              onChange={(e) => setPeMax(e.target.value)}
              style={{ width: "5rem", marginLeft: "0.25rem" }}
            />
          </label>
          <label>
            D/E max
            <input
              type="number"
              value={deMax}
              onChange={(e) => setDeMax(e.target.value)}
              style={{ width: "5rem", marginLeft: "0.25rem" }}
            />
          </label>
          <label>
            FCF min
            <input
              type="number"
              value={fcfMin}
              onChange={(e) => setFcfMin(e.target.value)}
              style={{ width: "5rem", marginLeft: "0.25rem" }}
            />
          </label>
          <button type="submit">Run</button>
        </div>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {loading ? (
        <p>Loading…</p>
      ) : (
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

