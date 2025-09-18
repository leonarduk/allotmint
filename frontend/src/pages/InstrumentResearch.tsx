import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentHistoryChart } from "../components/InstrumentHistoryChart";
import { getScreener, getNews, getQuotes } from "../api";
import type { ScreenerResult, NewsItem, QuoteRow } from "../types";
import EmptyState from "../components/EmptyState";
import { largeNumber, money, percent } from "../lib/money";
import { useConfig } from "../ConfigContext";
import { formatDateISO } from "../lib/date";
import tableStyles from "../styles/table.module.css";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";

type ActiveTab = "fundamentals" | "timeseries" | "news";

type TimeseriesRow = {
  date: string;
  close_gbp: number;
  change_gbp: number;
  change_pct: number;
};

const toNum = (value: unknown): number =>
  typeof value === "number" && Number.isFinite(value) ? value : NaN;

export default function InstrumentResearch() {
  const { ticker } = useParams<{ ticker: string }>();
  const [metrics, setMetrics] = useState<ScreenerResult | null>(null);
  const [days, setDays] = useState(30);
  const [showBollinger, setShowBollinger] = useState(false);
  const { t } = useTranslation();
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";
  const { tabs, disabledTabs, baseCurrency } = useConfig();
  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
  } = useInstrumentHistory(tkr, days);
  const historyPrices = detail?.mini?.[String(days)] ?? [];
  const [quote, setQuote] = useState<QuoteRow | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [screenerError, setScreenerError] = useState<string | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("fundamentals");
  const [inWatchlist, setInWatchlist] = useState(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return !!tkr && list.includes(tkr);
  });

  const timeseriesRows = useMemo<TimeseriesRow[]>(() => {
    const priceEntries = Array.isArray((detail as any)?.prices)
      ? ((detail as any).prices as Array<{
          date?: unknown;
          close?: unknown;
          close_gbp?: unknown;
        }>)
      : [];

    const raw = priceEntries
      .map((entry) => ({
        date: typeof entry.date === "string" ? entry.date : "",
        close_gbp: toNum(entry.close_gbp ?? entry.close),
      }))
      .filter((item): item is { date: string; close_gbp: number } =>
        Boolean(item.date) && Number.isFinite(item.close_gbp),
      );

    return raw.map((price, index, arr) => {
      const prev = arr[index - 1];
      const change_gbp = prev ? price.close_gbp - prev.close_gbp : NaN;
      const change_pct = prev ? (change_gbp / prev.close_gbp) * 100 : NaN;
      return {
        date: price.date,
        close_gbp: price.close_gbp,
        change_gbp,
        change_pct,
      };
    });
  }, [detail]);

  useEffect(() => {
    if (!tkr) return;
    const screenerCtrl = new AbortController();
    const newsCtrl = new AbortController();
    const quoteCtrl = new AbortController();

    const fetchScreener = async () => {
      setScreenerLoading(true);
      setScreenerError(null);
      try {
        const rows = await getScreener([tkr], {}, screenerCtrl.signal);
        setMetrics(rows[0] || null);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setMetrics(null);
        setScreenerError(err instanceof Error ? err.message : String(err));
      } finally {
        setScreenerLoading(false);
      }
    };

    const fetchQuote = async () => {
      setQuoteLoading(true);
      setQuoteError(null);
      try {
        const rows = await getQuotes([tkr], quoteCtrl.signal);
        setQuote(rows[0] || null);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setQuote(null);
        setQuoteError(err instanceof Error ? err.message : String(err));
      } finally {
        setQuoteLoading(false);
      }
    };

    const fetchNews = async () => {
      setNewsLoading(true);
      setNewsError(null);
      try {
        const items = await getNews(tkr, newsCtrl.signal);
        setNews(items);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setNews([]);
        setNewsError(err instanceof Error ? err.message : String(err));
      } finally {
        setNewsLoading(false);
      }
    };

    void fetchScreener();
    void fetchQuote();
    void fetchNews();
    return () => {
      screenerCtrl.abort();
      newsCtrl.abort();
      quoteCtrl.abort();
    };
  }, [tkr]);

  useEffect(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setInWatchlist(!!tkr && list.includes(tkr));
  }, [tkr]);

  function toggleWatchlist() {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!tkr) return;
    if (list.includes(tkr)) {
      const updated = list.filter((s) => s !== tkr);
      localStorage.setItem("watchlistSymbols", updated.join(","));
      setInWatchlist(false);
    } else {
      list.push(tkr);
      localStorage.setItem("watchlistSymbols", list.join(","));
      setInWatchlist(true);
    }
  }

  if (!tkr) return <div>Invalid ticker</div>;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      {(() => {
        const headingName = quote?.name ?? metrics?.name ?? detail?.name ?? null;
        if (!headingName) {
          return <div style={{ marginBottom: "1rem" }}>{tkr}</div>;
        }
        return (
          <h1 style={{ marginBottom: "1rem" }}>
            {tkr} {` - ${headingName}`}
            {detail?.sector || detail?.currency ? (
              <span
                style={{
                  display: "block",
                  fontSize: "0.8rem",
                  fontWeight: "normal",
                }}
              >
                {detail?.sector ?? ""}
                {detail?.sector && detail?.currency ? " · " : ""}
                {detail?.currency ?? ""}
              </span>
            ) : null}
          </h1>
        );
      })()}

      <div style={{ marginBottom: "1rem" }}>
        {tabs.screener && !(disabledTabs ?? []).includes("screener") && (
          <Link to="/screener" style={{ marginRight: "1rem" }}>
            View Screener
          </Link>
        )}
        {tabs.watchlist && !(disabledTabs ?? []).includes("watchlist") && (
          <Link to="/watchlist">Watchlist</Link>
        )}
        <button onClick={toggleWatchlist} style={{ marginLeft: "1rem" }}>
          {inWatchlist ? "Remove from Watchlist" : "Add to Watchlist"}
        </button>
      </div>
      {detail && (
        <div style={{ marginBottom: "1rem" }}>
          <h2>Instrument info</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {detail.name && <li>Name: {detail.name}</li>}
            {detail.sector && <li>Sector: {detail.sector}</li>}
            {detail.currency && <li>Currency: {detail.currency}</li>}
          </ul>
        </div>
      )}
      <div style={{ marginBottom: "0.5rem" }}>
        {[7, 30, 180, 365].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            disabled={days === d}
            style={{ marginRight: "0.5rem" }}
          >
            {d}d
          </button>
        ))}
        <label style={{ marginLeft: "1rem", fontSize: "0.85rem" }}>
          <input
            type="checkbox"
            checked={showBollinger}
            onChange={(e) => setShowBollinger(e.target.checked)}
          />{" "}
          {t("instrumentDetail.bollingerBands")}
        </label>
      </div>
      {detailError && !detailLoading ? (
        <div
          style={{
            height: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          History unavailable
        </div>
      ) : (
        <InstrumentHistoryChart
          data={historyPrices}
          loading={detailLoading}
          showBollinger={showBollinger}
        />
      )}
      <div style={{ margin: "1rem 0" }}>
        {([
          ["fundamentals", "Fundamentals"],
          ["timeseries", "Timeseries"],
          ["news", "News"],
        ] as const).map(([tab, label]) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            disabled={activeTab === tab}
            style={{
              marginRight: "0.5rem",
              padding: "0.4rem 0.8rem",
              cursor: activeTab === tab ? "default" : "pointer",
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {activeTab === "fundamentals" && (
        <>
          {(quoteLoading && screenerLoading) ? (
            <div>Loading quote...</div>
          ) : quoteError || screenerError ? (
            <div>{quoteError || screenerError}</div>
          ) : (
            (quote || metrics) && (
              <table style={{ marginBottom: "1rem" }}>
                <tbody>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Price
                    </th>
                    <td>{quote?.last ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Change %
                    </th>
                    <td>
                      {quote?.changePct != null
                        ? `${quote.changePct.toFixed(2)}%`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Day Range
                    </th>
                    <td>
                      {quote
                        ? `${quote.low ?? "—"} - ${quote.high ?? "—"}`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      52W Range
                    </th>
                    <td>
                      {metrics
                        ? `${metrics.low_52w ?? "—"} - ${metrics.high_52w ?? "—"}`
                        : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
            )
          )}
          {screenerLoading ? (
            <div>Loading metrics...</div>
          ) : screenerError ? (
            <div>{screenerError}</div>
          ) : (
            metrics && (
              <table style={{ marginBottom: "1rem" }}>
                <tbody>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      PEG
                    </th>
                    <td>{metrics.peg_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      P/E
                    </th>
                    <td>{metrics.pe_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      D/E
                    </th>
                    <td>{metrics.de_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      LT D/E
                    </th>
                    <td>{metrics.lt_de_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Market Cap
                    </th>
                    <td>{largeNumber(metrics.market_cap)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      EPS
                    </th>
                    <td>{metrics.eps ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Dividend Yield
                    </th>
                    <td>{metrics.dividend_yield ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Beta
                    </th>
                    <td>{metrics.beta ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Avg Volume
                    </th>
                    <td>{largeNumber(metrics.avg_volume)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Interest Coverage
                    </th>
                    <td>{metrics.interest_coverage ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Current Ratio
                    </th>
                    <td>{metrics.current_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Quick Ratio
                    </th>
                    <td>{metrics.quick_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      FCF
                    </th>
                    <td>{largeNumber(metrics.fcf)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Gross Margin
                    </th>
                    <td>{metrics.gross_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Operating Margin
                    </th>
                    <td>{metrics.operating_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Net Margin
                    </th>
                    <td>{metrics.net_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      EBITDA Margin
                    </th>
                    <td>{metrics.ebitda_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROA
                    </th>
                    <td>{metrics.roa ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROE
                    </th>
                    <td>{metrics.roe ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROI
                    </th>
                    <td>{metrics.roi ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Dividend Payout Ratio
                    </th>
                    <td>{metrics.dividend_payout_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Shares Outstanding
                    </th>
                    <td>{largeNumber(metrics.shares_outstanding)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Float Shares
                    </th>
                    <td>{largeNumber(metrics.float_shares)}</td>
                  </tr>
                </tbody>
              </table>
            )
          )}
        </>
      )}
      {activeTab === "timeseries" && (
        <table style={{ marginBottom: "1rem", width: "100%" }}>
          <thead>
            <tr>
              <th className={tableStyles.cell}>{t("instrumentDetail.priceColumns.date")}</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {t("instrumentDetail.priceColumns.close")}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {t("instrumentDetail.priceColumns.delta")}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {t("instrumentDetail.priceColumns.deltaPct")}
              </th>
            </tr>
          </thead>
          <tbody>
            {detailLoading ? (
              <tr>
                <td
                  colSpan={4}
                  className={`${tableStyles.cell} ${tableStyles.center}`}
                  style={{ color: "#888" }}
                >
                  {t("app.loading")}
                </td>
              </tr>
            ) : detailError ? (
              <tr>
                <td colSpan={4} className={`${tableStyles.cell} ${tableStyles.center}`}>
                  {detailError.message}
                </td>
              </tr>
            ) : timeseriesRows.length ? (
              timeseriesRows
                .slice(-60)
                .reverse()
                .map((row) => {
                  const colour = Number.isFinite(row.change_gbp)
                    ? row.change_gbp >= 0
                      ? "lightgreen"
                      : "red"
                    : undefined;
                  return (
                    <tr key={row.date}>
                      <td className={tableStyles.cell}>
                        {formatDateISO(new Date(row.date))}
                      </td>
                      <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                        {money(row.close_gbp, baseCurrency)}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                        style={{ color: colour }}
                      >
                        {money(row.change_gbp, baseCurrency)}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                        style={{ color: colour }}
                      >
                        {Number.isFinite(row.change_pct) ? (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "flex-end",
                              gap: "0.25rem",
                              fontVariantNumeric: "tabular-nums",
                            }}
                          >
                            {row.change_pct >= 0 ? (
                              <ArrowUpRight size={12} />
                            ) : (
                              <ArrowDownRight size={12} />
                            )}
                            {percent(row.change_pct, 2)}
                          </span>
                        ) : (
                          percent(row.change_pct, 2)
                        )}
                      </td>
                    </tr>
                  );
                })
            ) : (
              <tr>
                <td
                  colSpan={4}
                  className={`${tableStyles.cell} ${tableStyles.center}`}
                  style={{ color: "#888" }}
                >
                  {t("instrumentDetail.noPriceData")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {activeTab === "news" && (
        newsLoading ? (
          <div>Loading news...</div>
        ) : newsError ? (
          <div>{newsError}</div>
        ) : news.length === 0 ? (
          <EmptyState message="No news available" />
        ) : (
          <div>
            <h2>News</h2>
            <ul>
              {news.map((n, i) => (
                <li key={i}>
                  <a href={n.url} target="_blank" rel="noopener noreferrer">
                    {n.headline}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )
      )}
      {detailLoading ? (
        <div>Loading instrument details...</div>
      ) : detailError ? (
        <div>{detailError.message}</div>
      ) : (
        detail && detail.positions && detail.positions.length > 0 && (
          <div>
            <h2>Positions</h2>
            <ul>
              {detail.positions.map((p, i) => (
                <li key={i}>
                  {p.owner} – {p.account} : {p.units}
                </li>
              ))}
            </ul>
          </div>
        )
      )}
    </div>
  );
}
