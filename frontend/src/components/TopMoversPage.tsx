import {useCallback, useEffect, useMemo, useState} from "react";
import {useNavigate} from "react-router-dom";

import {getTopMovers, getGroupInstruments, getTradingSignals} from "../api";
import type {MoverRow, TradingSignal} from "../types";
import {WATCHLISTS, type WatchlistName} from "../data/watchlists";
import {InstrumentDetail} from "./InstrumentDetail";

import {useFetch} from "../hooks/useFetch";
import {useSortableTable} from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";

const PERIODS = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365} as const;
type PeriodKey = keyof typeof PERIODS;
type WatchlistOption = WatchlistName | "Portfolio";
const WATCHLIST_OPTIONS: WatchlistOption[] = [
  ...(Object.keys(WATCHLISTS) as WatchlistName[]),
  "Portfolio",
];

export function TopMoversPage() {
  const [watchlist, setWatchlist] = useState<WatchlistOption>("Portfolio");
  const [period, setPeriod] = useState<PeriodKey>("1d");
  const [selected, setSelected] = useState<MoverRow | null>(null);
  const navigate = useNavigate();
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(true);
  const [signalsError, setSignalsError] = useState<string | null>(null);

  const fetchMovers = useCallback(() => {
    if (watchlist === "Portfolio") {
      return getGroupInstruments("all").then((rows) =>
        getTopMovers(
          rows.map((r) => r.ticker),
          PERIODS[period]
        )
      );
    }
    return getTopMovers(WATCHLISTS[watchlist], PERIODS[period]);
  }, [watchlist, period]);
  const {data, loading, error} = useFetch(fetchMovers, [watchlist, period]);
  const rows = useMemo(() => {
    if (!data) return [];
    return [...data.gainers, ...data.losers];
  }, [data]);

  const {sorted, handleSort} = useSortableTable<MoverRow>(rows, "change_pct");

  useEffect(() => {
    getTradingSignals()
      .then(setSignals)
      .catch((e) => setSignalsError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSignalsLoading(false));
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{color: "red"}}>{error.message}</p>;

  return (
    <>
      <div style={{marginBottom: "0.5rem"}}>
        <select
          value={watchlist}
          onChange={(e) => setWatchlist(e.target.value as WatchlistOption)}
          style={{marginRight: "0.5rem"}}
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
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={() => setSelected(r)}
                  style={{
                    color: "dodgerblue",
                    textDecoration: "underline",
                    background: "none",
                    border: "none",
                    padding: 0,
                    font: "inherit",
                    cursor: "pointer",
                  }}
                >
                  {r.ticker}
                </button>
              </td>
              <td className={tableStyles.cell}>{r.name}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{color: r.change_pct >= 0 ? "green" : "red"}}
              >
                {r.change_pct.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {signalsLoading ? (
        <p>Loading…</p>
      ) : signalsError ? (
        <p style={{color: "red"}}>{signalsError}</p>
      ) : signals.length === 0 ? (
        <p>No signals.</p>
      ) : (
        <table
          style={{width: "100%", borderCollapse: "collapse", marginTop: "1rem"}}
        >
          <thead>
            <tr>
              <th style={{textAlign: "left", padding: "4px"}}>Ticker</th>
              <th style={{textAlign: "left", padding: "4px"}}>Action</th>
              <th style={{textAlign: "left", padding: "4px"}}>Reason</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.ticker}>
                <td style={{padding: "4px"}}>
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/instrument/${s.ticker}`);
                    }}
                  >
                    {s.ticker}
                  </a>
                </td>
                <td style={{padding: "4px"}}>{s.action}</td>
                <td style={{padding: "4px"}}>{s.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
