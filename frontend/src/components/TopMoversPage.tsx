import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getTopMovers,
  getGroupInstruments,
  getTradingSignals,
  getGroupMovers,
} from "../api";
import type { MoverRow, TradingSignal } from "../types";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import { InstrumentDetail } from "./InstrumentDetail";

import { useFetch } from "../hooks/useFetch";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";

const PERIODS = { "1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365 } as const;
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
  const [needsLogin, setNeedsLogin] = useState(false);
  const [portfolioTotal, setPortfolioTotal] = useState<number | null>(null);
  const [excludeSmall, setExcludeSmall] = useState(false);

  const MIN_WEIGHT = 0.5;

  const fetchMovers = useCallback(async () => {
    if (watchlist === "Portfolio") {
      try {
        const rows = await getGroupInstruments("all");
        const total = rows.reduce(
          (sum, r) => sum + (r.market_value_gbp ?? 0),
          0,
        );
        setPortfolioTotal(total);
        setNeedsLogin(false);
        return getGroupMovers(
          "all",
          PERIODS[period],
          10,
          excludeSmall ? MIN_WEIGHT : 0,
        );
      } catch (e) {
        if (e instanceof Error && /^HTTP 401/.test(e.message)) {
          setNeedsLogin(true);
          setWatchlist("FTSE 100");
          setPortfolioTotal(null);
          return getTopMovers(WATCHLISTS["FTSE 100"], PERIODS[period]);
        }
        throw e;
      }
    }
    setPortfolioTotal(null);
    return getTopMovers(WATCHLISTS[watchlist], PERIODS[period]);
  }, [watchlist, period, excludeSmall]);
  const { data, loading, error } = useFetch(fetchMovers, [watchlist, period, excludeSmall]);
  type ExtendedMoverRow = MoverRow & {
    delta_gbp?: number | null;
    pct_portfolio?: number | null;
  };
  const rows: ExtendedMoverRow[] = useMemo(() => {
    if (!data) return [];
    const combined = [...data.gainers, ...data.losers];
    if (watchlist === "Portfolio") {
      return combined.map((r) => ({
        ...r,
        delta_gbp:
          r.market_value_gbp != null
            ? (r.market_value_gbp * r.change_pct) / 100
            : null,
        pct_portfolio:
          r.market_value_gbp != null && portfolioTotal
            ? (r.market_value_gbp / portfolioTotal) * 100
            : null,
      }));
    }
    return combined;
  }, [data, watchlist, portfolioTotal]);

  const { sorted, handleSort } = useSortableTable<ExtendedMoverRow>(
    rows,
    "change_pct",
  );

  useEffect(() => {
    getTradingSignals()
      .then(setSignals)
      .catch((e) =>
        setSignalsError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setSignalsLoading(false));
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error) {
    const match = error.message.match(/^HTTP (\d+)\s+[–-]\s+(.*)$/);
    const status = match?.[1];
    const msg = match?.[2] ?? error.message;
    return (
      <p style={{ color: "red" }}>
        Failed to load movers{status ? ` (HTTP ${status})` : ""}: {msg}
      </p>
    );
  }

  return (
    <>
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          Watchlist:
          <select
            value={watchlist}
            onChange={(e) => setWatchlist(e.target.value as WatchlistOption)}
            style={{ marginLeft: "0.25rem" }}
          >
            {WATCHLIST_OPTIONS.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Period:
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as PeriodKey)}
            style={{ marginLeft: "0.25rem" }}
          >
            {(Object.keys(PERIODS) as PeriodKey[]).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        {watchlist === "Portfolio" && (
          <label style={{ marginLeft: "0.5rem" }}>
            <input
              type="checkbox"
              checked={excludeSmall}
              onChange={(e) => setExcludeSmall(e.target.checked)}
              style={{ marginRight: "0.25rem" }}
            />
            Exclude positions &lt;{MIN_WEIGHT}%
          </label>
        )}
      </div>

      {needsLogin && (
        <p style={{ color: "red" }}>
          Please log in to view portfolio-based movers.
        </p>
      )}

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
            {watchlist === "Portfolio" && (
              <>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ £</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>% of portfolio</th>
              </>
            )}
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
                style={{ color: r.change_pct >= 0 ? "green" : "red" }}
              >
                {r.change_pct.toFixed(2)}
              </td>
              {watchlist === "Portfolio" && (
                <>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {r.delta_gbp != null ? r.delta_gbp.toFixed(2) : ""}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {r.pct_portfolio != null
                      ? r.pct_portfolio.toFixed(2)
                      : ""}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {signalsLoading ? (
        <p>Loading…</p>
      ) : signalsError ? (
        <p style={{ color: "red" }}>{signalsError}</p>
      ) : signals.length === 0 ? (
        <p>No signals.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "1rem" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "4px" }}>Ticker</th>
              <th style={{ textAlign: "left", padding: "4px" }}>Action</th>
              <th style={{ textAlign: "left", padding: "4px" }}>Reason</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.ticker}>
                <td style={{ padding: "4px" }}>
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
                <td style={{ padding: "4px" }}>{s.action}</td>
                <td style={{ padding: "4px" }}>{s.reason}</td>
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
