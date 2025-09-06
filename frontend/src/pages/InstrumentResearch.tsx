import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getInstrumentDetail, getScreener } from "../api";
import type { ScreenerResult, InstrumentDetail } from "../types";

export default function InstrumentResearch() {
  const { ticker } = useParams<{ ticker: string }>();
  const [detail, setDetail] = useState<InstrumentDetail | null>(null);
  const [metrics, setMetrics] = useState<ScreenerResult | null>(null);
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";
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
    return () => {
      detailCtrl.abort();
      screenerCtrl.abort();
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
        <Link to="/screener" style={{ marginRight: "1rem" }}>
          View Screener
        </Link>
        <Link to="/watchlist">Watchlist</Link>
        <button onClick={toggleWatchlist} style={{ marginLeft: "1rem" }}>
          {inWatchlist ? "Remove from Watchlist" : "Add to Watchlist"}
        </button>
      </div>
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
