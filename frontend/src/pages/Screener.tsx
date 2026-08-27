import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { checkScreenerAvailable, getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import { InstrumentDetail } from "../components/InstrumentDetail";
import InfoTip from "../components/InfoTip";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import i18n from "../i18n";

const RATIO_COLUMN_TIPS: Record<
  string,
  { key: string; defaultText: string; anchor: string }
> = {
  PEG: { key: "peg", defaultText: "P/E ratio divided by the expected earnings growth rate.", anchor: "peg-ratio" },
  "P/E": { key: "pe", defaultText: "Share price divided by earnings per share.", anchor: "pe-ratio" },
  "D/E": { key: "de", defaultText: "Total debt divided by shareholders' equity — a measure of financial leverage.", anchor: "debt-equity" },
  "LT D/E": { key: "ltDe", defaultText: "Long-term debt divided by shareholders' equity.", anchor: "lt-debt-equity" },
  IntCov: { key: "interestCoverage", defaultText: "Operating earnings (EBIT) divided by interest expense.", anchor: "interest-coverage" },
  Curr: { key: "currentRatio", defaultText: "Current assets divided by current liabilities.", anchor: "current-ratio" },
  Quick: { key: "quickRatio", defaultText: "Liquid assets, excluding inventory, divided by current liabilities.", anchor: "quick-ratio" },
  FCF: { key: "fcf", defaultText: "Cash generated from operations minus capital expenditure.", anchor: "free-cash-flow" },
  EPS: { key: "eps", defaultText: "Net income divided by the number of shares outstanding.", anchor: "eps" },
  "Gross Margin": { key: "grossMargin", defaultText: "Gross profit divided by revenue.", anchor: "gross-margin" },
  "Op Margin": { key: "operatingMargin", defaultText: "Operating income divided by revenue.", anchor: "operating-margin" },
  "Net Margin": { key: "netMargin", defaultText: "Net income divided by revenue.", anchor: "net-margin" },
  "EBITDA Margin": { key: "ebitdaMargin", defaultText: "EBITDA divided by revenue.", anchor: "ebitda-margin" },
  ROA: { key: "roa", defaultText: "Net income divided by total assets.", anchor: "roa" },
  ROE: { key: "roe", defaultText: "Net income divided by shareholders' equity.", anchor: "roe" },
  ROI: { key: "roi", defaultText: "The gain from an investment divided by its cost.", anchor: "roi" },
  "Div%": { key: "dividendYield", defaultText: "Annual dividend per share divided by share price.", anchor: "dividend-yield" },
  Payout: { key: "dividendPayoutRatio", defaultText: "Dividends paid divided by net income.", anchor: "dividend-payout-ratio" },
  Beta: { key: "beta", defaultText: "A measure of how sensitive a stock's price is to overall market movements.", anchor: "beta" },
  Shares: { key: "sharesOutstanding", defaultText: "The total number of a company's shares currently held by all shareholders.", anchor: "shares-outstanding" },
  Float: { key: "floatShares", defaultText: "Shares outstanding that are freely tradable, excluding closely held or restricted shares.", anchor: "float-shares" },
  MktCap: { key: "marketCap", defaultText: "Share price multiplied by shares outstanding.", anchor: "market-cap" },
  "52wH": { key: "high52w", defaultText: "The highest trading price over the past 52 weeks.", anchor: "week-52-high" },
  "52wL": { key: "low52w", defaultText: "The lowest trading price over the past 52 weeks.", anchor: "week-52-low" },
  AvgVol: { key: "avgVolume", defaultText: "The average number of shares traded per day over a recent period.", anchor: "avg-volume" },
};

function RatioHeaderInfoTip({ column }: { column: string }) {
  const { t } = useTranslation();
  const tip = RATIO_COLUMN_TIPS[column];
  if (!tip) return null;
  return (
    <InfoTip
      label={t("screener.tips.infoLabel", "What does {{column}} mean?", { column })}
      to={`/metrics-explained#${tip.anchor}`}
    >
      {t(`screener.tips.${tip.key}`, tip.defaultText)}
    </InfoTip>
  );
}

export function Screener() {
  const [watchlist, setWatchlist] = useState<WatchlistName | "Custom">(
    "Custom",
  );
  const [tickers, setTickers] = useState("");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [ltDeMax, setLtDeMax] = useState("");
  const [interestCoverageMin, setInterestCoverageMin] = useState("");
  const [currentRatioMin, setCurrentRatioMin] = useState("");
  const [quickRatioMin, setQuickRatioMin] = useState("");
  const [fcfMin, setFcfMin] = useState("");
  const [epsMin, setEpsMin] = useState("");
  const [grossMarginMin, setGrossMarginMin] = useState("");
  const [operatingMarginMin, setOperatingMarginMin] = useState("");
  const [netMarginMin, setNetMarginMin] = useState("");
  const [ebitdaMarginMin, setEbitdaMarginMin] = useState("");
  const [roaMin, setRoaMin] = useState("");
  const [roeMin, setRoeMin] = useState("");
  const [roiMin, setRoiMin] = useState("");
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
  const [selected, setSelected] = useState<ScreenerResult | null>(null);
  // Optimistic default: assume the screener is available until the cheap
  // probe below says otherwise, so the form still renders synchronously
  // (no flash of a loading state) when the feature is actually enabled.
  const [screenerAvailable, setScreenerAvailable] = useState(true);
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;
    checkScreenerAvailable().then((available) => {
      if (!cancelled && available === false) setScreenerAvailable(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const { sorted, handleSort } = useSortableTable(rows, "rank");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols =
      watchlist === "Custom"
        ? tickers
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
        : WATCHLISTS[watchlist];
    if (!symbols.length) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getScreener(symbols, {
        peg_max: pegMax ? parseFloat(pegMax) : undefined,
        pe_max: peMax ? parseFloat(peMax) : undefined,
        de_max: deMax ? parseFloat(deMax) : undefined,
        lt_de_max: ltDeMax ? parseFloat(ltDeMax) : undefined,
        interest_coverage_min: interestCoverageMin
          ? parseFloat(interestCoverageMin)
          : undefined,
        current_ratio_min: currentRatioMin
          ? parseFloat(currentRatioMin)
          : undefined,
        quick_ratio_min: quickRatioMin
          ? parseFloat(quickRatioMin)
          : undefined,
        fcf_min: fcfMin ? parseFloat(fcfMin) : undefined,
        eps_min: epsMin ? parseFloat(epsMin) : undefined,
        gross_margin_min: grossMarginMin
          ? parseFloat(grossMarginMin)
          : undefined,
        operating_margin_min: operatingMarginMin
          ? parseFloat(operatingMarginMin)
          : undefined,
        net_margin_min: netMarginMin ? parseFloat(netMarginMin) : undefined,
        ebitda_margin_min: ebitdaMarginMin
          ? parseFloat(ebitdaMarginMin)
          : undefined,
        roa_min: roaMin ? parseFloat(roaMin) : undefined,
        roe_min: roeMin ? parseFloat(roeMin) : undefined,
        roi_min: roiMin ? parseFloat(roiMin) : undefined,
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
      const status = (e as { status?: number } | undefined)?.status;
      if (status === 402) {
        // Genuinely unavailable in this deployment -- never surface the raw
        // backend detail (it names an internal package and a repo URL).
        // Keep the technical detail in the console only (#7221).
        console.error("Screener request rejected (feature unavailable):", e);
        setScreenerAvailable(false);
        setError(t("screener.unavailableBody"));
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-1 text-2xl">{t("screener.title")}</h1>
      <p className="mb-4">{t("screener.description")}</p>

      {!screenerAvailable && (
        <p
          role="status"
          style={{
            background: "#fff4e5",
            border: "1px solid #f0ad4e",
            color: "#333",
            padding: "0.5rem 1rem",
            marginBottom: "1rem",
          }}
        >
          {t("screener.unavailableBody")}
        </p>
      )}

      {screenerAvailable && (
        <form
          onSubmit={handleSubmit}
          className="mb-4 flex flex-wrap items-center gap-2"
        >
          <label className="mr-2">
            Watchlist
            <select
              value={watchlist}
              onChange={(e) =>
                setWatchlist(e.target.value as WatchlistName | "Custom")
              }
              className="ml-1 border px-2 py-1"
              aria-label="Watchlist"
            >
              <option value="Custom">Custom</option>
              {(Object.keys(WATCHLISTS) as WatchlistName[]).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {watchlist === "Custom" && (
            <label className="mr-2">
              {t("screener.tickers")}
              <input
                aria-label={t("screener.tickers")}
                type="text"
                value={tickers}
                onChange={(e) => setTickers(e.target.value)}
                placeholder="PFE,MSFT,…"
                style={{ marginLeft: "0.25rem" }}
              />
            </label>
          )}
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
            {t("screener.maxLtDe")}
            <input
              aria-label={t("screener.maxLtDe")}
              type="number"
              value={ltDeMax}
              onChange={(e) => setLtDeMax(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minInterestCoverage")}
            <input
              aria-label={t("screener.minInterestCoverage")}
              type="number"
              value={interestCoverageMin}
              onChange={(e) => setInterestCoverageMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minCurrentRatio")}
            <input
              aria-label={t("screener.minCurrentRatio")}
              type="number"
              value={currentRatioMin}
              onChange={(e) => setCurrentRatioMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minQuickRatio")}
            <input
              aria-label={t("screener.minQuickRatio")}
              type="number"
              value={quickRatioMin}
              onChange={(e) => setQuickRatioMin(e.target.value)}
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
            {t("screener.minEps")}
            <input
              aria-label={t("screener.minEps")}
              type="number"
              value={epsMin}
              onChange={(e) => setEpsMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minGrossMargin")}
            <input
              aria-label={t("screener.minGrossMargin")}
              type="number"
              value={grossMarginMin}
              onChange={(e) => setGrossMarginMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minOperatingMargin")}
            <input
              aria-label={t("screener.minOperatingMargin")}
              type="number"
              value={operatingMarginMin}
              onChange={(e) => setOperatingMarginMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minNetMargin")}
            <input
              aria-label={t("screener.minNetMargin")}
              type="number"
              value={netMarginMin}
              onChange={(e) => setNetMarginMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minEbitdaMargin")}
            <input
              aria-label={t("screener.minEbitdaMargin")}
              type="number"
              value={ebitdaMarginMin}
              onChange={(e) => setEbitdaMarginMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minRoa")}
            <input
              aria-label={t("screener.minRoa")}
              type="number"
              value={roaMin}
              onChange={(e) => setRoaMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minRoe")}
            <input
              aria-label={t("screener.minRoe")}
              type="number"
              value={roeMin}
              onChange={(e) => setRoeMin(e.target.value)}
              step="any"
              style={{ marginLeft: "0.25rem" }}
            />
          </label>
          <label style={{ marginRight: "0.5rem" }}>
            {t("screener.minRoi")}
            <input
              aria-label={t("screener.minRoi")}
              type="number"
              value={roiMin}
              onChange={(e) => setRoiMin(e.target.value)}
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
            {t("screener.max52WeekLow")}
            <input
              aria-label={t("screener.max52WeekLow")}
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
      )}

      {screenerAvailable && error && <p style={{ color: "red" }}>{error}</p>}
      {loading && <p>{t("screener.loading")}</p>}

      {rows.length > 0 && !loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={right} onClick={() => handleSort("rank")}>Rank</th>
              <th
                style={{ ...cell, cursor: "pointer" }}
                onClick={() => handleSort("ticker")}
              >
                Ticker
              </th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>
                PEG
                <RatioHeaderInfoTip column="PEG" />
              </th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>
                P/E
                <RatioHeaderInfoTip column="P/E" />
              </th>
              <th style={right} onClick={() => handleSort("de_ratio")}>
                D/E
                <RatioHeaderInfoTip column="D/E" />
              </th>
              <th style={right} onClick={() => handleSort("lt_de_ratio")}>
                LT D/E
                <RatioHeaderInfoTip column="LT D/E" />
              </th>
              <th style={right} onClick={() => handleSort("interest_coverage")}>
                IntCov
                <RatioHeaderInfoTip column="IntCov" />
              </th>
              <th style={right} onClick={() => handleSort("current_ratio")}>
                Curr
                <RatioHeaderInfoTip column="Curr" />
              </th>
              <th style={right} onClick={() => handleSort("quick_ratio")}>
                Quick
                <RatioHeaderInfoTip column="Quick" />
              </th>
              <th style={right} onClick={() => handleSort("fcf")}>
                FCF
                <RatioHeaderInfoTip column="FCF" />
              </th>
              <th style={right} onClick={() => handleSort("eps")}>
                EPS
                <RatioHeaderInfoTip column="EPS" />
              </th>
              <th style={right} onClick={() => handleSort("gross_margin")}>
                Gross Margin
                <RatioHeaderInfoTip column="Gross Margin" />
              </th>
              <th style={right} onClick={() => handleSort("operating_margin")}>
                Op Margin
                <RatioHeaderInfoTip column="Op Margin" />
              </th>
              <th style={right} onClick={() => handleSort("net_margin")}>
                Net Margin
                <RatioHeaderInfoTip column="Net Margin" />
              </th>
              <th style={right} onClick={() => handleSort("ebitda_margin")}>
                EBITDA Margin
                <RatioHeaderInfoTip column="EBITDA Margin" />
              </th>
              <th style={right} onClick={() => handleSort("roa")}>
                ROA
                <RatioHeaderInfoTip column="ROA" />
              </th>
              <th style={right} onClick={() => handleSort("roe")}>
                ROE
                <RatioHeaderInfoTip column="ROE" />
              </th>
              <th style={right} onClick={() => handleSort("roi")}>
                ROI
                <RatioHeaderInfoTip column="ROI" />
              </th>
              <th style={right} onClick={() => handleSort("dividend_yield")}>
                Div%
                <RatioHeaderInfoTip column="Div%" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("dividend_payout_ratio")}
              >
                Payout
                <RatioHeaderInfoTip column="Payout" />
              </th>
              <th style={right} onClick={() => handleSort("beta")}>
                Beta
                <RatioHeaderInfoTip column="Beta" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("shares_outstanding")}
              >
                Shares
                <RatioHeaderInfoTip column="Shares" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("float_shares")}
              >
                Float
                <RatioHeaderInfoTip column="Float" />
              </th>
              <th style={right} onClick={() => handleSort("market_cap")}>
                MktCap
                <RatioHeaderInfoTip column="MktCap" />
              </th>
              <th style={right} onClick={() => handleSort("high_52w")}>
                52wH
                <RatioHeaderInfoTip column="52wH" />
              </th>
              <th style={right} onClick={() => handleSort("low_52w")}>
                52wL
                <RatioHeaderInfoTip column="52wL" />
              </th>
              <th style={right} onClick={() => handleSort("avg_volume")}>
                AvgVol
                <RatioHeaderInfoTip column="AvgVol" />
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={`${r.ticker}-${r.rank}`}
                onClick={() => setSelected(r)}
                style={{ cursor: "pointer" }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    setSelected(r);
                  }
                }}
              >
                <td style={right}>{r.rank}</td>
                <td style={cell}>{r.ticker}</td>
                <td style={right}>{r.peg_ratio ?? "—"}</td>
                <td style={right}>{r.pe_ratio ?? "—"}</td>
                <td style={right}>{r.de_ratio ?? "—"}</td>
                <td style={right}>{r.lt_de_ratio ?? "—"}</td>
                <td style={right}>{r.interest_coverage ?? "—"}</td>
                <td style={right}>{r.current_ratio ?? "—"}</td>
                <td style={right}>{r.quick_ratio ?? "—"}</td>
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
                <td style={right}>{r.eps ?? "—"}</td>
                <td style={right}>{r.gross_margin ?? "—"}</td>
                <td style={right}>{r.operating_margin ?? "—"}</td>
                <td style={right}>{r.net_margin ?? "—"}</td>
                <td style={right}>{r.ebitda_margin ?? "—"}</td>
                <td style={right}>{r.roa ?? "—"}</td>
                <td style={right}>{r.roe ?? "—"}</td>
                <td style={right}>{r.roi ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name ?? selected.ticker}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default Screener;

