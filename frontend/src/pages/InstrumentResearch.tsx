import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentHistoryChart } from "../components/InstrumentHistoryChart";
import { getInstrumentDetail, getScreener, getNews, getQuotes } from "../api";
import type { ScreenerResult, InstrumentDetail, NewsItem, QuoteRow } from "../types";
import { largeNumber } from "../lib/money";

export default function InstrumentResearch() {
  const { ticker } = useParams<{ ticker: string }>();
  const [detail, setDetail] = useState<InstrumentDetail | null>(null);
  const [metrics, setMetrics] = useState<ScreenerResult | null>(null);
  const [days, setDays] = useState(30);
  const [showBollinger, setShowBollinger] = useState(false);
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";
  const {
    data: history,
    loading: historyLoading,
    error: historyError,
  } = useInstrumentHistory(tkr, days);
  const historyPrices = history?.[String(days)] ?? [];
  const [quote, setQuote] = useState<QuoteRow | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [inWatchlist, setInWatchlist] = useState(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return !!tkr && list.includes(tkr);
  });

  useEffect(() => {
    if (!tkr) return;
    const detailCtrl = new AbortController();
    const screenerCtrl = new AbortController();
    const newsCtrl = new AbortController();
    getInstrumentDetail(tkr, 365, detailCtrl.signal)
      .then(setDetail)
      .catch((err) => {
        if (err.name !== "AbortError") console.error(err);
      });
    getScreener([tkr], {}, screenerCtrl.signal)
      .then((rows) => setMetrics(rows[0] || null))
      .catch((err) => {
        if (err.name !== "AbortError") console.error(err);
      });
    getQuotes([tkr])
      .then((rows) => setQuote(rows[0] || null))
      .catch((err) => console.error(err));
    getNews(tkr, newsCtrl.signal)
      .then(setNews)
      .catch((err) => {
        if (err.name !== "AbortError") console.error(err);
      });
    return () => {
      detailCtrl.abort();
      screenerCtrl.abort();
      newsCtrl.abort();
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
      <h1 style={{ marginBottom: "1rem" }}>{tkr}</h1>
      <div style={{ marginBottom: "1rem" }}>
        {tabs.screener && !disabledTabs.includes("screener") && (
          <Link to="/screener" style={{ marginRight: "1rem" }}>
            View Screener
          </Link>
        )}
        {tabs.watchlist && !disabledTabs.includes("watchlist") && (
          <Link to="/watchlist">Watchlist</Link>
        )}
        <button onClick={toggleWatchlist} style={{ marginLeft: "1rem" }}>
          {inWatchlist ? "Remove from Watchlist" : "Add to Watchlist"}
        </button>
      </div>
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
      {historyError && !historyLoading ? (
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
          loading={historyLoading}
          showBollinger={showBollinger}
        />
      )}
      {(quote || metrics) && (
        <table style={{ marginBottom: "1rem" }}>
          <tbody>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Price</th>
              <td>{quote?.last ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Change %</th>
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
      )}
      {metrics && (
        <table style={{ marginBottom: "1rem" }}>
          <tbody>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>PEG</th>
              <td>{metrics.peg_ratio ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>P/E</th>
              <td>{metrics.pe_ratio ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>D/E</th>
              <td>{metrics.de_ratio ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>LT D/E</th>
              <td>{metrics.lt_de_ratio ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Market Cap</th>
              <td>{largeNumber(metrics.market_cap)}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>EPS</th>
              <td>{metrics.eps ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Dividend Yield</th>
              <td>{metrics.dividend_yield ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Beta</th>
              <td>{metrics.beta ?? "—"}</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>Avg Volume</th>
              <td>{largeNumber(metrics.avg_volume)}</td>
            </tr>
          </tbody>
        </table>
      )}
      {detail && detail.positions && detail.positions.length > 0 && (
        <div>
          <h2>Positions</h2>
          <ul>
            {detail.positions.map((p, i) => (
              <li key={i}>{p.owner} – {p.account} : {p.units}</li>
            ))}
          </ul>
        </div>
      )}
      {news.length > 0 && (
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
      )}
    </div>
  );
}
