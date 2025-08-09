import { useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { useSortableTable } from "../hooks/useSortableTable";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";

const WATCHLIST = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"];

export function ScreenerPage() {
  const {
    data: rows,
    loading,
    error,
  } = useFetch<ScreenerResult[]>(() => getScreener(WATCHLIST), []);
  const [ticker, setTicker] = useState<string | null>(null);

  const { sorted, handleSort } = useSortableTable(rows ?? [], "peg_ratio");

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;

  return (
    <>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort("ticker")}
            >
              Ticker
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("peg_ratio")}
            >
              PEG
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("pe_ratio")}
            >
              P/E
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("de_ratio")}
            >
              D/E
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("fcf")}
            >
              FCF
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.ticker}
              onClick={() => setTicker(r.ticker)}
              className={tableStyles.clickable}
            >
              <td className={tableStyles.cell}>{r.ticker}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {r.peg_ratio ?? "—"}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {r.pe_ratio ?? "—"}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {r.de_ratio ?? "—"}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {r.fcf != null ? r.fcf.toLocaleString() : "—"}
              </td>
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
