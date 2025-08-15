import { useCallback, useMemo, useState } from "react";
import { getTopMovers, getGroupMovers } from "../api";
import type { MoverRow } from "../types";
import { WATCHLISTS } from "../data/watchlists";
import { useFetch } from "../hooks/useFetch";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";

const PERIODS = { "1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365 } as const;
type PeriodKey = keyof typeof PERIODS;

export function TopMoversPage() {
  type WatchlistOption = keyof typeof WATCHLISTS | "Portfolio";
  const WATCHLIST_OPTIONS: WatchlistOption[] = [
    ...(Object.keys(WATCHLISTS) as (keyof typeof WATCHLISTS)[]),
    "Portfolio",
  ];
  const [watchlist, setWatchlist] = useState<WatchlistOption>("FTSE 100");
  const [period, setPeriod] = useState<PeriodKey>("1d");

  const fetchMovers = useCallback(() => {
    if (watchlist === "Portfolio") {
      return getGroupMovers("all", PERIODS[period]);
    }
    return getTopMovers(
      WATCHLISTS[watchlist as keyof typeof WATCHLISTS],
      PERIODS[period],
    );
  }, [watchlist, period]);
  const { data, loading, error } = useFetch(fetchMovers, [watchlist, period]);
  const rows = useMemo(() => {
    if (!data) return [];
    return [...data.gainers, ...data.losers];
  }, [data]);

  const { sorted, handleSort } = useSortableTable<MoverRow>(
    rows,
    "change_pct",
  );

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;

  return (
    <>
      <div style={{ marginBottom: "0.5rem" }}>
        <select
          value={watchlist}
          onChange={(e) => setWatchlist(e.target.value as WatchlistOption)}
          style={{ marginRight: "0.5rem" }}
        >
          {WATCHLIST_OPTIONS.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value as PeriodKey)}
        >
          {(Object.keys(PERIODS) as PeriodKey[]).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

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
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort("name")}
            >
              Name
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("change_pct")}
            >
              %
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.ticker}>
              <td className={tableStyles.cell}>{r.ticker}</td>
              <td className={tableStyles.cell}>{r.name}</td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {r.change_pct.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
