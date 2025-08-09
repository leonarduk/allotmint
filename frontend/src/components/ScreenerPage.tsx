import { useEffect, useState } from "react";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import styles from "../styles/table.module.css";
import { useSortableTable } from "../hooks/useSortableTable";

const WATCHLIST = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"];

export function ScreenerPage() {
  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [ticker, setTicker] = useState<string | null>(null);

  useEffect(() => {
    getScreener(WATCHLIST).then(setRows).catch(() => setRows([]));
  }, []);

  const { sorted, handleSort } = useSortableTable(rows, "peg_ratio");

  return (
    <>
      <table className={styles.table}>
        <thead>
          <tr>
            <th
              className={`${styles.cell} ${styles.clickable}`}
              onClick={() => handleSort("ticker")}
            >
              Ticker
            </th>
            <th
              className={`${styles.cell} ${styles.right} ${styles.clickable}`}
              onClick={() => handleSort("peg_ratio")}
            >
              PEG
            </th>
            <th
              className={`${styles.cell} ${styles.right} ${styles.clickable}`}
              onClick={() => handleSort("pe_ratio")}
            >
              P/E
            </th>
            <th
              className={`${styles.cell} ${styles.right} ${styles.clickable}`}
              onClick={() => handleSort("de_ratio")}
            >
              D/E
            </th>
            <th
              className={`${styles.cell} ${styles.right} ${styles.clickable}`}
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
              className={styles.clickable}
            >
              <td className={styles.cell}>{r.ticker}</td>
              <td className={`${styles.cell} ${styles.right}`}>{r.peg_ratio ?? "—"}</td>
              <td className={`${styles.cell} ${styles.right}`}>{r.pe_ratio ?? "—"}</td>
              <td className={`${styles.cell} ${styles.right}`}>{r.de_ratio ?? "—"}</td>
              <td className={`${styles.cell} ${styles.right}`}>
                {r.fcf != null ? r.fcf.toLocaleString() : "—"}
              </td>
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
