import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getOpportunities, getGroupInstruments } from "../api";
import { ALL_PORTFOLIOS_SLUG } from "../constants/portfolios";
import type { OpportunityEntry } from "../types";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import { InstrumentDetail } from "./InstrumentDetail";
import { SignalBadge } from "./SignalBadge";
import {
  ChecksSkippedBadge,
  SignalFactors,
  SignalStrength,
} from "./SignalDetails";
import { formatSignalAction } from "../utils/formatSignalAction";
import TableRowsSkeleton from "./skeletons/TableRowsSkeleton";
import TextSkeleton from "./skeletons/TextSkeleton";
import LoadingStatus from "./skeletons/LoadingStatus";
import InfoTip from "./InfoTip";

import { useFetch } from "../hooks/useFetch";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import { loadJSON, saveJSON } from "../utils/storage";
import { MAX_TRADING_SIGNAL_ROWS } from "../constants/renderLimits";

const PERIODS = { "1d": 1, "1w": 7, "1m": 30, "3m": 90, "1y": 365 } as const;
type PeriodKey = keyof typeof PERIODS;
type WatchlistOption = WatchlistName | "Portfolio";
const WATCHLIST_OPTIONS: WatchlistOption[] = [
  ...(Object.keys(WATCHLISTS) as WatchlistName[]),
  "Portfolio",
];

/**
 * `useFetch` initialises `loading` to `false` and only flips it to `true`
 * inside a `useEffect`, so the very first render (before that effect
 * flushes) has `loading === false` and `data === null`. A bare `loading`
 * check would fall through to the "no signals" empty state for that frame
 * (#7229). Extracted as a pure, exported function and unit tested directly
 * (see TopMoversPage.test.tsx) because that pre-effect frame is not
 * independently observable through RTL's act()-wrapped `render`: by the
 * time any assertion runs against the rendered component, React has already
 * flushed the effect and `loading` is true on its own, so a JSX-level test
 * cannot tell this derivation apart from a bare `loading` check.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function computeMoversLoading(
  loading: boolean,
  data: unknown,
  error: unknown,
): boolean {
  return loading || (data == null && error == null);
}

export function TopMoversPage() {
  const reporting = useReportingCurrency();
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
        setFallbackError(null);
        // The holdings total (for "% of portfolio") and the movers themselves
        // are independent, so fetch them concurrently rather than chaining a
        // second slow round trip behind the first (#7788 item 4).
        const [holdings, opportunities] = await Promise.all([
          getGroupInstruments(ALL_PORTFOLIOS_SLUG),
          getOpportunities({
            group: ALL_PORTFOLIOS_SLUG,
            days: PERIODS[period],
            limit: 10,
            minWeight: excludeSmall ? MIN_WEIGHT : 0,
          }),
        ]);
        setPortfolioTotal(
          holdings.reduce((sum, r) => sum + (r.market_value_gbp ?? 0), 0),
        );
        setNeedsLogin(false);
        return opportunities;
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
  const { data, loading, error, refetch } = useFetch(fetchMovers, [watchlist, period, excludeSmall]);
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

  // Descending by default: the backend returns the top N gainers *and* the
  // top N losers, and an ascending sort pushed every gainer below the losers
  // (#7788 item 2).
  const { sorted, handleSort } = useSortableTable<ExtendedMoverRow>(
    rows,
    "change_pct",
    false,
  );

  const colSpan = watchlist === "Portfolio" ? 6 : 4;
  const visibleSignals = data?.signals.slice(0, MAX_TRADING_SIGNAL_ROWS) ?? [];
  const loadingLabel = t("movers.loading");
  // See `computeMoversLoading` above for why this can't be a bare `loading`
  // check.
  const isLoading = computeMoversLoading(loading, data, error);

  const disclaimer = (
    <p style={{ color: "#64748b", fontSize: "0.875rem", marginBottom: "0.25rem" }}>
      {t("trading.description")}
    </p>
  );

  if (error != null) {
    const match = error?.message.match(/^HTTP (\d+)\s+[–-]\s+(.*)$/);
    const status = match?.[1];
    const msg = match?.[2] ?? error?.message;
    return (
      <div>
        {disclaimer}
        <p role="alert" style={{ color: "red" }}>
          {t("movers.loadFailed", {
            status: status ? ` (HTTP ${status})` : "",
          })}
          : {msg}
        </p>
        <button type="button" onClick={refetch}>
          {t("common.retry")}
        </button>
      </div>
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
      {disclaimer}
      <p
        id="movers-window-note"
        style={{ color: "#64748b", fontSize: "0.875rem", marginBottom: "0.5rem" }}
      >
        {t("movers.windowNote")}
      </p>
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

      {isLoading && (
        <LoadingStatus label={loadingLabel}>
          <span aria-hidden="true" />
        </LoadingStatus>
      )}

      {/* No scroll box or virtualisation: the list is capped at the top 10
          gainers plus top 10 losers, and a clipped scroll box hid rows that
          the Signals table below still listed (#7788 item 3). */}
      <div style={{ overflowX: "auto" }}>
      <table className={tableStyles.table}>
        <thead>
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
            <th className={tableStyles.cell}>
              {t("movers.signal")}
              <InfoTip
                label={t("movers.signalInfoLabel", "What does the Signal column mean?")}
                to="/metrics-explained#buy-sell-signal"
              >
                {t(
                  "movers.signalInfo",
                  "Shows whether the latest signal generated for that instrument, using the same strategy thresholds as the Trading page, was a buy or sell candidate."
                )}
              </InfoTip>
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("change_pct")}
              title={t("movers.pctChangeHeader", { period })}
            >
              {t("movers.pctChangeHeader", { period })}
            </th>
            {watchlist === "Portfolio" && (
              <>
                <th
                  className={`${tableStyles.cell} ${tableStyles.right}`}
                  title={t("movers.deltaGbpHeader", { period, symbol: reporting.symbol })}
                >
                  {t("movers.deltaGbpHeader", { period, symbol: reporting.symbol })}
                </th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t("movers.pctPortfolio")}
                </th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <TableRowsSkeleton
              rows={8}
              colSpan={colSpan}
              label=""
              cellClassName={tableStyles.cell}
            />
          ) : (
            <>
              {sorted.map((r, index) => {
                return (
                  <tr key={`${r.ticker}-${index}`}>
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
                          {r.delta_gbp != null ? reporting.convertGbp(r.delta_gbp).toFixed(2) : ""}
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
            </>
          )}
        </tbody>
      </table>
      </div>
      {isLoading ? (
        <p style={{ marginTop: "0.5rem" }} aria-hidden="true">
          <TextSkeleton width="12rem" label="" />
        </p>
      ) : !data || data.signals.length === 0 ? (
        <p>{t("trading.noSignals")}</p>
      ) : (
        <section aria-labelledby="movers-signals-title" style={{ marginTop: "1rem" }}>
          <h2 id="movers-signals-title" style={{ fontSize: "1.125rem", fontWeight: 600 }}>
            {t("movers.signalsTableTitle")}
          </h2>
          <p style={{ color: "#64748b", fontSize: "0.875rem", marginBottom: "0.25rem" }}>
            {t("movers.signalsTableNote", { period })}
          </p>
          <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "4px" }}>{t("common.ticker")}</th>
                <th style={{ textAlign: "left", padding: "4px" }}>{t("common.action")}</th>
                <th style={{ textAlign: "left", padding: "4px" }}>
                  {t("trading.columns.strengthHeader")}
                </th>
                <th style={{ textAlign: "left", padding: "4px" }}>{t("common.reason")}</th>
                <th style={{ textAlign: "left", padding: "4px" }}>
                  {t("trading.columns.why")}
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleSignals.map((s, index) => (
                <tr key={`${s.ticker}-${index}`}>
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
                  <td style={{ padding: "4px" }}>
                    {formatSignalAction(s.action)}
                    <ChecksSkippedBadge checksSkipped={s.checks_skipped} />
                  </td>
                  <td style={{ padding: "4px" }}>
                    <SignalStrength confidence={s.confidence} />
                  </td>
                  <td style={{ padding: "4px" }}>{s.reason}</td>
                  <td style={{ padding: "4px" }}>
                    <SignalFactors factors={s.factors} rationale={s.rationale} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {data.signals.length > MAX_TRADING_SIGNAL_ROWS && (
            <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", color: "#64748b" }}>
              {t("topMoversPage.showingFirst", {
                shown: MAX_TRADING_SIGNAL_ROWS.toLocaleString(),
                total: data.signals.length.toLocaleString(),
              })}
            </p>
          )}
        </section>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected.row.ticker}
          name={selected.row.name}
          instrument_type={selected.row.instrument_type}
          signal={selected.row.signal ?? undefined}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
