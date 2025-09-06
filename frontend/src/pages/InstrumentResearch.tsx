import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getInstrumentDetail, getScreener, getQuotes } from "../api";
import type { ScreenerResult, InstrumentDetail, QuoteRow } from "../types";

export default function InstrumentResearch() {
  const { ticker } = useParams<{ ticker: string }>();
  const [detail, setDetail] = useState<InstrumentDetail | null>(null);
  const [metrics, setMetrics] = useState<ScreenerResult | null>(null);
  const [quote, setQuote] = useState<QuoteRow | null>(null);
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";

  useEffect(() => {
    if (!tkr) return;
    const detailCtrl = new AbortController();
    const screenerCtrl = new AbortController();
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
    return () => {
      detailCtrl.abort();
      screenerCtrl.abort();
    };
  }, [tkr]);

  if (!tkr) return <div>Invalid ticker</div>;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h1 style={{ marginBottom: "1rem" }}>{tkr}</h1>
      <div style={{ marginBottom: "1rem" }}>
        <Link to="/screener" style={{ marginRight: "1rem" }}>
          View Screener
        </Link>
        <Link to="/watchlist">Watchlist</Link>
      </div>
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
    </div>
  );
}
