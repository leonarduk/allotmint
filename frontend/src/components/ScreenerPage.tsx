import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { useSortableTable } from "../hooks/useSortableTable";
import { useFetch } from "../hooks/useFetch";

const WATCHLIST = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"];

export function ScreenerPage() {
  const {
    data: rows,
    loading,
    error,
  } = useFetch<ScreenerResult[]>(() => getScreener(WATCHLIST), []);
  const [ticker, setTicker] = useState<string | null>(null);

  const { sorted, handleSort } = useSortableTable(rows ?? [], "peg_ratio");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;

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
          name={rows?.find((r) => r.ticker === ticker)?.name ?? ""}
          onClose={() => setTicker(null)}
        />
      )}
    </>
  );
}
