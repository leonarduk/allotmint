import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { useSortableTable } from "../hooks/useSortableTable";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import i18n from "../i18n";


export function ScreenerPage() {
  const { t } = useTranslation();
  const [watchlist, setWatchlist] = useState<WatchlistName>("FTSE 100");
  const fetchScreener = useCallback(
    () => getScreener(WATCHLISTS[watchlist]),
    [watchlist]
  );
  const {
    data: rows,
    loading,
    error,
  } = useFetch<ScreenerResult[]>(fetchScreener, [watchlist]);
  const [ticker, setTicker] = useState<string | null>(null);

  const { sorted, handleSort } = useSortableTable(rows ?? [], "peg_ratio");

  if (loading) return <p>{t("common.loading")}</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;

  return (
    <>
      <label style={{ display: "inline-block", marginBottom: "0.5rem" }}>
        {t("screener.watchlist")}
        <select
          value={watchlist}
          onChange={(e) => setWatchlist(e.target.value as WatchlistName)}
          style={{ marginLeft: "0.25rem" }}
        >
          {(Object.keys(WATCHLISTS) as WatchlistName[]).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

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
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  setTicker(r.ticker);
                }
              }}
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
                {r.fcf != null
                  ? new Intl.NumberFormat(i18n.language).format(r.fcf)
                  : "—"}
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
