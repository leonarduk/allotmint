import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getOpportunities, getGroupInstruments } from "../api";
import type { OpportunityEntry } from "../types";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import { InstrumentDetail } from "./InstrumentDetail";
import { SignalBadge } from "./SignalBadge";

import { useFetch } from "../hooks/useFetch";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import { useVirtualizer } from "@tanstack/react-virtual";
import { loadJSON, saveJSON } from "../utils/storage";

const PERIODS = { "1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365 } as const;
type PeriodKey = keyof typeof PERIODS;
type WatchlistOption = WatchlistName | "Portfolio";
const WATCHLIST_OPTIONS: WatchlistOption[] = [
  ...(Object.keys(WATCHLISTS) as WatchlistName[]),
  "Portfolio",
];

export function TopMoversPage() {
  const [watchlist, setWatchlist] = useState<WatchlistOption>(() =>
    loadJSON<WatchlistOption>("topMovers.watchlist", "Portfolio"),
  );
  const [period, setPeriod] = useState<PeriodKey>(() =>
    loadJSON<PeriodKey>("topMovers.period", "1d"),
  );
  const [selected, setSelected] = useState<
    { row: OpportunityEntry } | null
  >(null);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [needsLogin, setNeedsLogin] = useState(false);
  const [portfolioTotal, setPortfolioTotal] = useState<number | null>(null);
  const [excludeSmall, setExcludeSmall] = useState(() =>
    loadJSON<boolean>("topMovers.excludeSmall", false),
  );
  const [fallbackError, setFallbackError] = useState<string | null>(null);

  const MIN_WEIGHT = 0.5;

  useEffect(() => {
    saveJSON("topMovers.watchlist", watchlist);
  }, [watchlist]);
  useEffect(() => {
    saveJSON("topMovers.period", period);
  }, [period]);
  useEffect(() => {
    saveJSON("topMovers.excludeSmall", excludeSmall);
  }, [excludeSmall]);

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
      } catch (e) {
        if (e instanceof Error && /^HTTP 401/.test(e.message)) {
          setNeedsLogin(true);
          setWatchlist("FTSE 100");
          setPortfolioTotal(null);
          return getOpportunities({
            tickers: WATCHLISTS["FTSE 100"],
            days: PERIODS[period],
            limit: 10,
          });
        }
        throw e;
      }

      try {
        setFallbackError(null);
        return await getOpportunities({
          group: "all",
          days: PERIODS[period],
          limit: 10,
          minWeight: excludeSmall ? MIN_WEIGHT : 0,
        });
      } catch (e) {
        if (e instanceof Error && /^HTTP 401/.test(e.message)) {
          setNeedsLogin(true);
          setWatchlist("FTSE 100");
          setPortfolioTotal(null);
          setFallbackError(e.message);
          return getOpportunities({
            tickers: WATCHLISTS["FTSE 100"],
            days: PERIODS[period],
            limit: 10,
          });
        }
        throw e;
      }
    }
    setPortfolioTotal(null);
    return getOpportunities({
      tickers: WATCHLISTS[watchlist],
      days: PERIODS[period],
      limit: 10,
    });
  }, [watchlist, period, excludeSmall]);
  const { data, loading, error } = useFetch(fetchMovers, [watchlist, period, excludeSmall]);
  type ExtendedMoverRow = OpportunityEntry & {
    delta_gbp?: number | null;
    pct_portfolio?: number | null;
  };
  const rows: ExtendedMoverRow[] = useMemo(() => {
    const entries = data?.entries ?? [];
    if (watchlist === "Portfolio") {
      return entries.map((r) => ({
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
    return entries;
  }, [data, watchlist, portfolioTotal]);

  const { sorted, handleSort } = useSortableTable<ExtendedMoverRow>(
    rows,
    "change_pct",
  );

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const tableHeaderRef = useRef<HTMLTableSectionElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  useEffect(() => {
    if (tableHeaderRef.current) {
      setHeaderHeight(tableHeaderRef.current.getBoundingClientRect().height);
    }
  }, []);

  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 40,
    overscan: 5,
    scrollMargin: headerHeight,
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length
    ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
    : 0;
  const items = virtualRows.length
    ? virtualRows
    : sorted.map((_, index) => ({ index, start: index * 40, end: (index + 1) * 40 }));
  const colSpan = watchlist === "Portfolio" ? 6 : 4;

  if (loading) return <p>{t("common.loading")}</p>;
  if (error != null) {
    const match = error?.message.match(/^HTTP (\d+)\s+[–-]\s+(.*)$/);
    const status = match?.[1];
    const msg = match?.[2] ?? error?.message;
    return (
      <p style={{ color: "red" }}>
        {t("movers.loadFailed", {
          status: status ? ` (HTTP ${status})` : "",
        })}
        : {msg}
      </p>
    );
  }

  const errorBanner = fallbackError
    ? (() => {
        const raw = fallbackError;
        const match = raw.match(/^HTTP (\d+)\s+[–-]\s+(.*)$/);
        const status = match?.[1];
        const msg = match?.[2] ?? raw;
        return (
          <p style={{ color: "red" }}>
            {t("movers.loadFailed", {
              status: status ? ` (HTTP ${status})` : "",
            })}
            : {msg}
          </p>
        );
      })()
    : null;

  return (
    <>
      {errorBanner}
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          {t("movers.watchlist")}
          <select
            value={watchlist}
            onChange={(e) => setWatchlist(e.target.value as WatchlistOption)}
            style={{ marginLeft: "0.25rem" }}
          >
            {WATCHLIST_OPTIONS.map((name) => (
              <option key={name} value={name}>
                {name === "Portfolio" ? t("portfolio") : name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("movers.period")}
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
            {t("movers.excludeSmall", { min: MIN_WEIGHT })}
          </label>
        )}
      </div>

      {needsLogin && (
        <p style={{ color: "red" }}>{t("movers.loginPrompt")}</p>
      )}

      <div
        ref={tableContainerRef}
        style={{ maxHeight: "60vh", overflowY: "auto", overflowX: "auto" }}
      >
      <table className={tableStyles.table}>
        <thead ref={tableHeaderRef}>
          <tr>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort("ticker")}
            >
              {t("common.ticker")}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort("name")}
            >
              {t("common.name")}
            </th>
            <th className={tableStyles.cell}>{t("movers.signal")}</th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("change_pct")}
            >
              %
            </th>
            {watchlist === "Portfolio" && (
              <>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ £</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t("movers.pctPortfolio")}
                </th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr style={{ height: paddingTop }}>
              <td colSpan={colSpan} style={{ padding: 0, border: 0 }} />
            </tr>
          )}
          {items.map((virtualRow) => {
            const r = sorted[virtualRow.index];
            return (
              <tr key={r.ticker}>
                <td className={tableStyles.cell}>
                  <button
                    type="button"
                    onClick={() => setSelected({ row: r })}
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
                <td className={tableStyles.cell}>
                  {r.signal ? (
                    <SignalBadge
                      action={r.signal.action}
                      reason={r.signal.reason}
                      confidence={r.signal.confidence}
                      rationale={r.signal.rationale}
                      onClick={() => setSelected({ row: r })}
                    />
                  ) : null}
                </td>
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
            );
          })}
          {paddingBottom > 0 && (
            <tr style={{ height: paddingBottom }}>
              <td colSpan={colSpan} style={{ padding: 0, border: 0 }} />
            </tr>
          )}
        </tbody>
      </table>
      </div>
      {!data ? (
        <p>{t("common.loading")}</p>
      ) : data.signals.length === 0 ? (
        <p>{t("trading.noSignals")}</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "1rem" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "4px" }}>{t("common.ticker")}</th>
              <th style={{ textAlign: "left", padding: "4px" }}>{t("common.action")}</th>
              <th style={{ textAlign: "left", padding: "4px" }}>{t("common.reason")}</th>
            </tr>
          </thead>
          <tbody>
            {data.signals.map((s) => (
              <tr key={s.ticker}>
                <td style={{ padding: "4px" }}>
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/research/${s.ticker}`);
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
          ticker={selected.row.ticker}
          name={selected.row.name}
          signal={selected.row.signal ?? undefined}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
