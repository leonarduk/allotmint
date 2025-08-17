import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import { InstrumentDetail } from "../components/InstrumentDetail";
import i18n from "../i18n";

export function Screener() {
  const [tickers, setTickers] = useState("");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [fcfMin, setFcfMin] = useState("");
  const [dividendYieldMin, setDividendYieldMin] = useState("");
  const [dividendPayoutRatioMax, setDividendPayoutRatioMax] = useState("");
  const [betaMax, setBetaMax] = useState("");
  const [sharesOutstandingMin, setSharesOutstandingMin] = useState("");
  const [floatSharesMin, setFloatSharesMin] = useState("");
  const [marketCapMin, setMarketCapMin] = useState("");
  const [high52wMax, setHigh52wMax] = useState("");
  const [low52wMin, setLow52wMin] = useState("");
  const [avgVolumeMin, setAvgVolumeMin] = useState("");

  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { t } = useTranslation();

  const { sorted, handleSort } = useSortableTable(rows, "peg_ratio");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols = tickers
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (!symbols.length) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getScreener(symbols, {
        peg_max: pegMax ? parseFloat(pegMax) : undefined,
        pe_max: peMax ? parseFloat(peMax) : undefined,
        de_max: deMax ? parseFloat(deMax) : undefined,
        fcf_min: fcfMin ? parseFloat(fcfMin) : undefined,
        dividend_yield_min: dividendYieldMin
          ? parseFloat(dividendYieldMin)
          : undefined,
        dividend_payout_ratio_max: dividendPayoutRatioMax
          ? parseFloat(dividendPayoutRatioMax)
          : undefined,
        beta_max: betaMax ? parseFloat(betaMax) : undefined,
        shares_outstanding_min: sharesOutstandingMin
          ? parseFloat(sharesOutstandingMin)
          : undefined,
        float_shares_min: floatSharesMin
          ? parseFloat(floatSharesMin)
          : undefined,
        market_cap_min: marketCapMin
          ? parseFloat(marketCapMin)
          : undefined,
        high_52w_max: high52wMax ? parseFloat(high52wMax) : undefined,
        low_52w_min: low52wMin ? parseFloat(low52wMin) : undefined,
        avg_volume_min: avgVolumeMin ? parseFloat(avgVolumeMin) : undefined,
      });
      setRows(data);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.tickers")}
          <input
            aria-label={t("screener.tickers")}
            type="text"
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
            placeholder="AAPL,MSFT,…"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPeg")}
          <input
            aria-label={t("screener.maxPeg")}
            type="number"
            value={pegMax}
            onChange={(e) => setPegMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPe")}
          <input
            aria-label={t("screener.maxPe")}
            type="number"
            value={peMax}
            onChange={(e) => setPeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxDe")}
          <input
            aria-label={t("screener.maxDe")}
            type="number"
            value={deMax}
            onChange={(e) => setDeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minFcf")}
          <input
            aria-label={t("screener.minFcf")}
            type="number"
            value={fcfMin}
            onChange={(e) => setFcfMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minDividendYield")}
          <input
            aria-label={t("screener.minDividendYield")}
            type="number"
            value={dividendYieldMin}
            onChange={(e) => setDividendYieldMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxDividendPayoutRatio")}
          <input
            aria-label={t("screener.maxDividendPayoutRatio")}
            type="number"
            value={dividendPayoutRatioMax}
            onChange={(e) => setDividendPayoutRatioMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxBeta")}
          <input
            aria-label={t("screener.maxBeta")}
            type="number"
            value={betaMax}
            onChange={(e) => setBetaMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minSharesOutstanding")}
          <input
            aria-label={t("screener.minSharesOutstanding")}
            type="number"
            value={sharesOutstandingMin}
            onChange={(e) => setSharesOutstandingMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minFloatShares")}
          <input
            aria-label={t("screener.minFloatShares")}
            type="number"
            value={floatSharesMin}
            onChange={(e) => setFloatSharesMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minMarketCap")}
          <input
            aria-label={t("screener.minMarketCap")}
            type="number"
            value={marketCapMin}
            onChange={(e) => setMarketCapMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.max52WeekHigh")}
          <input
            aria-label={t("screener.max52WeekHigh")}
            type="number"
            value={high52wMax}
            onChange={(e) => setHigh52wMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.min52WeekLow")}
          <input
            aria-label={t("screener.min52WeekLow")}
            type="number"
            value={low52wMin}
            onChange={(e) => setLow52wMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minAvgVolume")}
          <input
            aria-label={t("screener.minAvgVolume")}
            type="number"
            value={avgVolumeMin}
            onChange={(e) => setAvgVolumeMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <button type="submit" disabled={loading} style={{ marginLeft: "0.5rem" }}>
          {loading ? t("screener.loading") : t("screener.run")}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {loading && <p>{t("screener.loading")}</p>}

      {rows.length > 0 && !loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th
                style={{ ...cell, cursor: "pointer" }}
                onClick={() => handleSort("ticker")}
              >
                Ticker
              </th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>PEG</th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>P/E</th>
              <th style={right} onClick={() => handleSort("de_ratio")}>D/E</th>
              <th style={right} onClick={() => handleSort("fcf")}>FCF</th>
              <th style={right} onClick={() => handleSort("dividend_yield")}>
                Div%
              </th>
              <th
                style={right}
                onClick={() => handleSort("dividend_payout_ratio")}
              >
                Payout
              </th>
              <th style={right} onClick={() => handleSort("beta")}>Beta</th>
              <th
                style={right}
                onClick={() => handleSort("shares_outstanding")}
              >
                Shares
              </th>
              <th
                style={right}
                onClick={() => handleSort("float_shares")}
              >
                Float
              </th>
              <th style={right} onClick={() => handleSort("market_cap")}>
                MktCap
              </th>
              <th style={right} onClick={() => handleSort("high_52w")}>
                52wH
              </th>
              <th style={right} onClick={() => handleSort("low_52w")}>
                52wL
              </th>
              <th style={right} onClick={() => handleSort("avg_volume")}>
                AvgVol
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => setSelected(r.ticker)}
                style={{ cursor: "pointer" }}
              >
                <td style={cell}>{r.ticker}</td>
                <td style={right}>{r.peg_ratio ?? "—"}</td>
                <td style={right}>{r.pe_ratio ?? "—"}</td>
                <td style={right}>{r.de_ratio ?? "—"}</td>
                <td style={right}>
                  {r.fcf != null
                    ? new Intl.NumberFormat(i18n.language).format(r.fcf)
                    : "—"}
                </td>
                <td style={right}>{r.dividend_yield ?? "—"}</td>
                <td style={right}>{r.dividend_payout_ratio ?? "—"}</td>
                <td style={right}>{r.beta ?? "—"}</td>
                <td style={right}>
                  {r.shares_outstanding != null
                    ? new Intl.NumberFormat(i18n.language).format(
                        r.shares_outstanding,
                      )
                    : "—"}
                </td>
                <td style={right}>
                  {r.float_shares != null
                    ? new Intl.NumberFormat(i18n.language).format(
                        r.float_shares,
                      )
                    : "—"}
                </td>
                <td style={right}>
                  {r.market_cap != null
                    ? new Intl.NumberFormat(i18n.language).format(r.market_cap)
                    : "—"}
                </td>
                <td style={right}>{r.high_52w ?? "—"}</td>
                <td style={right}>{r.low_52w ?? "—"}</td>
                <td style={right}>
                  {r.avg_volume != null
                    ? new Intl.NumberFormat(i18n.language).format(r.avg_volume)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected}
          name={rows.find((r) => r.ticker === selected)?.name ?? ""}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default Screener;

