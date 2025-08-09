import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { useFetch } from "../hooks/useFetch";

const WATCHLIST = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"];

type SortKey = "ticker" | "peg_ratio" | "pe_ratio" | "de_ratio" | "fcf";

export function ScreenerPage() {
  const { data: rows = [], loading, error } = useFetch<ScreenerResult[]>(
    () => getScreener(WATCHLIST),
    []
  );
  const [sortKey, setSortKey] = useState<SortKey>("peg_ratio");
  const [asc, setAsc] = useState(true);
  const [ticker, setTicker] = useState<string | null>(null);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>Error: {error}</p>;

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
    <>
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
            <tr key={r.ticker} onClick={() => setTicker(r.ticker)} style={{ cursor: "pointer" }}>
              <td style={cell}>{r.ticker}</td>
              <td style={right}>{r.peg_ratio ?? "—"}</td>
              <td style={right}>{r.pe_ratio ?? "—"}</td>
              <td style={right}>{r.de_ratio ?? "—"}</td>
              <td style={right}>{r.fcf != null ? r.fcf.toLocaleString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {ticker && (
        <InstrumentDetail
          ticker={ticker}
          name={rows.find((r) => r.ticker === ticker)?.name ?? ""}
          onClose={() => setTicker(null)}
        />
      )}
    </>
  );
}
