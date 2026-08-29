import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  getAlphaVsBenchmark,
  getGroupAlphaVsBenchmark,
  getGroupMaxDrawdown,
  getGroupTrackingError,
  getMaxDrawdown,
  getTrackingError,
} from "../api";
import type {
  AlphaResponse,
  MaxDrawdownResponse,
  TrackingErrorResponse,
} from "../types";

const percentFormatter = new Intl.NumberFormat(undefined, {
  style: "percent",
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return percentFormatter.format(value);
};

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return numberFormatter.format(value);
};

export default function MetricsExplanation() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const owner = searchParams.get("owner");
  const group = searchParams.get("group");
  const benchmark = searchParams.get("benchmark") ?? "VWRL.L";
  const daysParam = searchParams.get("days");
  const parsedDays = daysParam ? Number.parseInt(daysParam, 10) : Number.NaN;
  const days = Number.isFinite(parsedDays) ? parsedDays : 365;

  const [alphaData, setAlphaData] = useState<AlphaResponse | null>(null);
  const [trackingData, setTrackingData] = useState<TrackingErrorResponse | null>(
    null,
  );
  const [drawdownData, setDrawdownData] = useState<MaxDrawdownResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const hasContext = Boolean(owner || group);
  const backTarget = useMemo(() => {
    if (group) return `/?group=${encodeURIComponent(group)}`;
    if (owner) return `/portfolio/${encodeURIComponent(owner)}`;
    return "/";
  }, [group, owner]);

  useEffect(() => {
    if (!hasContext) {
      setAlphaData(null);
      setTrackingData(null);
      setDrawdownData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const loadMetrics = group
      ? Promise.all([
          getGroupAlphaVsBenchmark(group, benchmark, days),
          getGroupTrackingError(group, benchmark, days),
          getGroupMaxDrawdown(group, days),
        ])
      : owner
      ? Promise.all([
          getAlphaVsBenchmark(owner, benchmark, days),
          getTrackingError(owner, benchmark, days),
          getMaxDrawdown(owner, days),
        ])
      : Promise.resolve<[AlphaResponse, TrackingErrorResponse, MaxDrawdownResponse]>(
          [
            { alpha_vs_benchmark: null, benchmark, series: [] },
            { tracking_error: null, benchmark, active_returns: [] },
            { max_drawdown: null, series: [] },
          ],
        );

    loadMetrics
      .then(([alpha, tracking, drawdown]) => {
        if (cancelled) return;
        setAlphaData(alpha);
        setTrackingData(tracking);
        setDrawdownData(drawdown);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [owner, group, benchmark, days, hasContext]);

  const contextDescription = useMemo(() => {
    if (group) return t("metricsExplanation.groupContext", { group });
    if (owner) return t("metricsExplanation.ownerContext", { owner });
    return t("metricsExplanation.noContext");
  }, [group, owner, t]);

  const alphaSeries = alphaData?.series ?? [];
  const alphaLatest = alphaSeries.length
    ? alphaSeries[alphaSeries.length - 1]
    : null;
  const activeReturns = trackingData?.active_returns ?? [];
  const drawdownSeries = drawdownData?.series ?? [];

  return (
    <main className="container mx-auto max-w-5xl space-y-10 p-4">
      <header className="space-y-2">
        <Link to={backTarget} className="inline-block text-blue-500 hover:underline">
          {t("metricsExplanation.backLink")}
        </Link>
        <h1 className="text-3xl font-bold">
          {t("metricsExplanation.title")}
        </h1>
        <p className="text-lg text-gray-300">{contextDescription}</p>
        <p className="text-sm text-gray-400">
          {t("metricsExplanation.parameters", { benchmark, days })}
        </p>
      </header>

      {!hasContext && (
        <p className="rounded border border-slate-700 bg-slate-900/60 p-4 text-sm text-gray-300">
          {t("metricsExplanation.missingContext")}
        </p>
      )}

      {error && (
        <p className="rounded border border-red-500 bg-red-950/40 p-4 text-sm text-red-200">
          {t("metricsExplanation.loadError", { message: error.message })}
        </p>
      )}

      {loading && (
        <p className="text-sm text-gray-400">{t("metricsExplanation.loading")}</p>
      )}

        <section className="space-y-4" id="alpha-vs-benchmark">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.alpha.title")}
        </h2>
        <p>{t("metricsExplanation.sections.alpha.summary")}</p>

        <div className="rounded border border-slate-700 bg-slate-900/60 p-4">
          <h3 className="text-xl font-semibold">
            {t("metricsExplanation.sections.alpha.headline")}
          </h3>
          <p className="text-sm text-gray-300">
            {t("metricsExplanation.sections.alpha.detail", {
              alpha: formatPercent(alphaData?.alpha_vs_benchmark ?? null),
              portfolio: formatPercent(
                alphaLatest?.portfolio_cumulative_return ??
                  alphaData?.portfolio_cumulative_return ??
                  null,
              ),
              benchmark: formatPercent(
                alphaLatest?.benchmark_cumulative_return ??
                  alphaData?.benchmark_cumulative_return ??
                  null,
              ),
            })}
          </p>
          <pre className="mt-3 overflow-auto rounded bg-slate-950/60 p-3 text-sm text-slate-200">
            {`Alpha = (Π (1 + r_portfolio)) - (Π (1 + r_benchmark))`}
          </pre>
        </div>

        {alphaSeries.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.alpha.breakdownHeading")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.alpha.breakdownIntro")}
            </p>
            <div className="max-h-80 overflow-auto rounded border border-slate-700">
              <table className="min-w-full divide-y divide-slate-700 text-sm">
                <thead className="bg-slate-900/80">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">
                      {t("metricsExplanation.dateColumn")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.portfolioCumulative")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.benchmarkCumulative")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.alphaCumulative")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {alphaSeries.map((row) => (
                    <tr key={row.date}>
                      <td className="whitespace-nowrap px-3 py-2">{row.date}</td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.portfolio_cumulative_return)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.benchmark_cumulative_return)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.excess_cumulative_return)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

        <section className="space-y-4" id="tracking-error">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.trackingError.title")}
        </h2>
        <p>{t("metricsExplanation.sections.trackingError.summary")}</p>

        <div className="rounded border border-slate-700 bg-slate-900/60 p-4">
          <h3 className="text-xl font-semibold">
            {t("metricsExplanation.sections.trackingError.headline")}
          </h3>
          <p className="text-sm text-gray-300">
            {t("metricsExplanation.sections.trackingError.detail", {
              trackingError: formatPercent(trackingData?.tracking_error ?? null),
              dailyStd: formatPercent(
                (trackingData?.daily_active_standard_deviation ?? null) ?? null,
              ),
            })}
          </p>
          <pre className="mt-3 overflow-auto rounded bg-slate-950/60 p-3 text-sm text-slate-200">
            {`Tracking Error = √252 × σ(r_portfolio − r_benchmark)`}
          </pre>
        </div>

        {activeReturns.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trackingError.breakdownHeading")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.trackingError.breakdownIntro")}
            </p>
            <div className="max-h-80 overflow-auto rounded border border-slate-700">
              <table className="min-w-full divide-y divide-slate-700 text-sm">
                <thead className="bg-slate-900/80">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">
                      {t("metricsExplanation.dateColumn")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.portfolioReturn")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.benchmarkReturn")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.activeReturn")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {activeReturns.map((row) => (
                    <tr key={row.date}>
                      <td className="whitespace-nowrap px-3 py-2">{row.date}</td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.portfolio_return)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.benchmark_return)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.active_return)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="space-y-4" id="max-drawdown">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.maxDrawdown.title")}
        </h2>
        <p>{t("metricsExplanation.sections.maxDrawdown.summary")}</p>

        <div className="rounded border border-slate-700 bg-slate-900/60 p-4">
          <h3 className="text-xl font-semibold">
            {t("metricsExplanation.sections.maxDrawdown.headline")}
          </h3>
          <p className="text-sm text-gray-300">
            {t("metricsExplanation.sections.maxDrawdown.detail", {
              drawdown: formatPercent(drawdownData?.max_drawdown ?? null),
              peakDate: drawdownData?.peak?.date ?? t("metricsExplanation.notAvailable"),
              peakValue: formatNumber(drawdownData?.peak?.value ?? null),
              troughDate:
                drawdownData?.trough?.date ?? t("metricsExplanation.notAvailable"),
              troughValue: formatNumber(drawdownData?.trough?.value ?? null),
            })}
          </p>
          <pre className="mt-3 overflow-auto rounded bg-slate-950/60 p-3 text-sm text-slate-200">
            {`Max Drawdown = min_t (Portfolio Value_t ÷ Rolling Peak_t − 1)`}
          </pre>
        </div>

        {drawdownSeries.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.maxDrawdown.breakdownHeading")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.maxDrawdown.breakdownIntro")}
            </p>
            <div className="max-h-80 overflow-auto rounded border border-slate-700">
              <table className="min-w-full divide-y divide-slate-700 text-sm">
                <thead className="bg-slate-900/80">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">
                      {t("metricsExplanation.dateColumn")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.portfolioValue")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.runningPeak")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("metricsExplanation.drawdownColumn")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {drawdownSeries.map((row) => (
                    <tr key={row.date}>
                      <td className="whitespace-nowrap px-3 py-2">{row.date}</td>
                      <td className="px-3 py-2 text-right">
                        {formatNumber(row.portfolio_value)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatNumber(row.running_max)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatPercent(row.drawdown)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.otherPerformance.title", "More performance measures")}
        </h2>
        <p>
          {t(
            "metricsExplanation.sections.otherPerformance.intro",
            "These also appear on the Performance page but don't need live data to explain."
          )}
        </p>
        <div className="space-y-4">
          <div id="time-weighted-return">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.otherPerformance.twr.title", "Time-Weighted Return")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.otherPerformance.twr.detail",
                "Time-weighted return measures the portfolio's compounded growth rate over the selected period by linking together each sub-period's return. It removes the effect of the timing and size of deposits and withdrawals, so it reflects how the underlying investments performed rather than when money moved in or out."
              )}
            </p>
          </div>
          <div id="xirr">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.otherPerformance.xirr.title", "XIRR")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.otherPerformance.xirr.detail",
                "XIRR is the annualised internal rate of return calculated from the portfolio's actual dated cash flows (deposits, withdrawals, and current value). Unlike time-weighted return, it is affected by the timing and size of those cash flows."
              )}
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.trading.title", "Trading signal terms")}
        </h2>
        <p>
          {t(
            "metricsExplanation.sections.trading.intro",
            "Terms used on the Trading page's strategy thresholds and signal table."
          )}
        </p>
        <div className="space-y-4">
          <div id="rsi">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.rsi.title", "RSI (Relative Strength Index)")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.rsi.detail",
                "RSI is a momentum indicator, scored 0-100, derived from recent price changes. “RSI buy below” and “RSI sell above” are the thresholds a signal's RSI value must reach — at or below the buy threshold, at or above the sell threshold — to be considered a buy or sell candidate. “RSI lookback” is the number of days of price history used to calculate it."
              )}
            </p>
          </div>
          <div id="moving-average">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.movingAverage.title", "Moving average (short / long)")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.movingAverage.detail",
                "A moving average is the average closing price over a fixed number of days. Signals compare a shorter-window average against a longer-window one; the two windows are configured separately as “Short moving average” and “Long moving average”."
              )}
            </p>
          </div>
          <div id="sharpe-ratio">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.sharpe.title", "Sharpe ratio")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.sharpe.detail",
                "Here, the Sharpe ratio is the annualised excess return over the configured risk-free rate, divided by the daily volatility of returns. “Minimum Sharpe ratio” is an optional filter threshold a signal's Sharpe ratio must meet, when that filter is enabled."
              )}
            </p>
          </div>
          <div id="debt-equity">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.debtEquity.title", "Debt/equity (D/E)")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.debtEquity.detail",
                "Debt/equity divides a company's total debt by its shareholders' equity — a measure of financial leverage. “Maximum debt/equity” is an optional filter threshold, when enabled."
              )}
            </p>
          </div>
          <div id="volatility">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.volatility.title", "Volatility")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.volatility.detail",
                "Here, volatility is the day-to-day (daily, not annualised) standard deviation of returns — how much the price has fluctuated from one day to the next. “Maximum volatility” is an optional filter threshold, when enabled."
              )}
            </p>
          </div>
          <div id="checks-skipped">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.trading.checksSkipped.title", "“Checks skipped”")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.trading.checksSkipped.detail",
                "This badge appears when an optional check that needs the allotmint-pro add-on could not run, because that add-on isn't installed. “compliance” means the trade was not checked against your compliance rules at all. “fundamental_screen” means the P/E and debt/equity filters (configured above) were not applied to this buy candidate."
              )}
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.screener.title", "Screener ratios")}
        </h2>
        <p>
          {t(
            "metricsExplanation.sections.screener.intro",
            "The Screener page filters instruments by these financial ratios."
          )}
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div id="peg-ratio">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.peg.title", "PEG ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.peg.detail", "P/E ratio divided by the expected earnings growth rate.")}</p>
          </div>
          <div id="pe-ratio">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.pe.title", "P/E ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.pe.detail", "Share price divided by earnings per share.")}</p>
          </div>
          <div id="lt-debt-equity">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.ltDe.title", "LT D/E ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.ltDe.detail", "Long-term debt divided by shareholders' equity.")}</p>
          </div>
          <div id="interest-coverage">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.interestCoverage.title", "Interest coverage")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.interestCoverage.detail", "Operating earnings (EBIT) divided by interest expense — how many times over a company could pay its interest from its earnings.")}</p>
          </div>
          <div id="current-ratio">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.currentRatio.title", "Current ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.currentRatio.detail", "Current assets divided by current liabilities.")}</p>
          </div>
          <div id="quick-ratio">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.quickRatio.title", "Quick ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.quickRatio.detail", "Liquid assets, excluding inventory, divided by current liabilities.")}</p>
          </div>
          <div id="free-cash-flow">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.fcf.title", "FCF (Free cash flow)")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.fcf.detail", "Cash generated from operations minus capital expenditure.")}</p>
          </div>
          <div id="eps">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.eps.title", "EPS (Earnings per share)")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.eps.detail", "Net income divided by the number of shares outstanding.")}</p>
          </div>
          <div id="gross-margin">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.grossMargin.title", "Gross margin")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.grossMargin.detail", "Gross profit divided by revenue.")}</p>
          </div>
          <div id="operating-margin">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.operatingMargin.title", "Operating margin")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.operatingMargin.detail", "Operating income divided by revenue.")}</p>
          </div>
          <div id="net-margin">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.netMargin.title", "Net margin")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.netMargin.detail", "Net income divided by revenue.")}</p>
          </div>
          <div id="ebitda-margin">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.ebitdaMargin.title", "EBITDA margin")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.ebitdaMargin.detail", "EBITDA (earnings before interest, tax, depreciation and amortisation) divided by revenue.")}</p>
          </div>
          <div id="roa">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.roa.title", "ROA (Return on assets)")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.roa.detail", "Net income divided by total assets.")}</p>
          </div>
          <div id="roe">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.roe.title", "ROE (Return on equity)")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.roe.detail", "Net income divided by shareholders' equity.")}</p>
          </div>
          <div id="roi">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.roi.title", "ROI (Return on investment)")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.roi.detail", "The gain from an investment divided by its cost.")}</p>
          </div>
          <div id="dividend-yield">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.dividendYield.title", "Dividend yield")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.dividendYield.detail", "Annual dividend per share divided by share price.")}</p>
          </div>
          <div id="dividend-payout-ratio">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.dividendPayoutRatio.title", "Dividend payout ratio")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.dividendPayoutRatio.detail", "Dividends paid divided by net income.")}</p>
          </div>
          <div id="beta">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.beta.title", "Beta")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.beta.detail", "A measure of how sensitive a stock's price is to overall market movements.")}</p>
          </div>
          <div id="shares-outstanding">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.sharesOutstanding.title", "Shares outstanding")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.sharesOutstanding.detail", "The total number of a company's shares currently held by all shareholders.")}</p>
          </div>
          <div id="float-shares">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.floatShares.title", "Float shares")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.floatShares.detail", "Shares outstanding that are freely tradable, excluding closely held or restricted shares.")}</p>
          </div>
          <div id="market-cap">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.marketCap.title", "Market cap")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.marketCap.detail", "Share price multiplied by shares outstanding.")}</p>
          </div>
          <div id="week-52-high">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.high52w.title", "52-week high")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.high52w.detail", "The highest trading price over the past 52 weeks.")}</p>
          </div>
          <div id="week-52-low">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.low52w.title", "52-week low")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.low52w.detail", "The lowest trading price over the past 52 weeks.")}</p>
          </div>
          <div id="avg-volume">
            <h3 className="font-semibold">{t("metricsExplanation.sections.screener.avgVolume.title", "Average volume")}</h3>
            <p className="text-sm text-gray-300">{t("metricsExplanation.sections.screener.avgVolume.detail", "The average number of shares traded per day over a recent period.")}</p>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.movers.title", "Movers signal")}
        </h2>
        <div id="buy-sell-signal">
          <div>
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.movers.signal.title", "Buy / Sell signal")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.movers.signal.detail",
                "Shows whether the latest signal generated for that instrument, using the same strategy thresholds as the Trading page, was a buy or sell candidate."
              )}
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.plot.title", "Plot garden terms")}
        </h2>
        <p>
          {t(
            "metricsExplanation.sections.plot.intro",
            "Plot is a garden-themed view of the same real portfolio data. Every term below maps back to a real figure."
          )}
        </p>
        <div className="space-y-4">
          <div id="beds">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.beds.title", "Beds")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.plot.beds.detail",
                "Each investment account is shown as a bed. Every holding within that account is a crop planted in it."
              )}
            </p>
          </div>
          <div id="growth-stages">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.growthStages.title", "Growth stages (Wilting → Sown → Sprouting → Leafing → Budding → Flowering → Fruiting → Bumper crop)")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.plot.growthStages.detail",
                "A crop's growth stage is set by that holding's total gain, as a percentage of what was paid for it — it does not depend on how long it has been held."
              )}
            </p>
            <ul className="mt-2 grid list-none gap-x-6 gap-y-1 text-sm text-gray-300 sm:grid-cols-2">
              <li id="wilting">{t("metricsExplanation.sections.plot.growthStages.wilting", "Wilting: total gain of -20% or below")}</li>
              <li id="sown">{t("metricsExplanation.sections.plot.growthStages.sown", "Sown: total gain between -20% (exclusive) and 0%")}</li>
              <li id="sprouting">{t("metricsExplanation.sections.plot.growthStages.sprouting", "Sprouting: total gain between 0% (exclusive) and 5%")}</li>
              <li id="leafing">{t("metricsExplanation.sections.plot.growthStages.leafing", "Leafing: total gain between 5% (exclusive) and 15%")}</li>
              <li id="budding">{t("metricsExplanation.sections.plot.growthStages.budding", "Budding: total gain between 15% (exclusive) and 30%")}</li>
              <li id="flowering">{t("metricsExplanation.sections.plot.growthStages.flowering", "Flowering: total gain between 30% (exclusive) and 60%")}</li>
              <li id="fruiting">{t("metricsExplanation.sections.plot.growthStages.fruiting", "Fruiting: total gain between 60% (exclusive) and 120%")}</li>
              <li id="bumper-crop">{t("metricsExplanation.sections.plot.growthStages.bumper", "Bumper crop: total gain above 120%")}</li>
            </ul>
          </div>
          <div id="propagator">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.propagator.title", "Propagator")}
            </h3>
            <p className="text-sm text-gray-300">
              {t(
                "metricsExplanation.sections.plot.propagator.detail",
                "Lists crops still inside their minimum holding period — the configured number of days a holding must be held before it becomes eligible to sell — counting down to the date each one clears it. This is a holding-period measure, separate from the gain-based growth stage above."
              )}
            </p>
          </div>
          <div id="water">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.water.title", "Water")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.plot.water.detail", "The number of trades left this month against the account's configured monthly trade limit.")}
            </p>
          </div>
          <div id="feed">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.feed.title", "Feed")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.plot.feed.detail", "The remaining tax-allowance headroom for the current period.")}
            </p>
          </div>
          <div id="sunlight">
            <h3 className="text-lg font-semibold">
              {t("metricsExplanation.sections.plot.sunlight.title", "Sunlight")}
            </h3>
            <p className="text-sm text-gray-300">
              {t("metricsExplanation.sections.plot.sunlight.detail", "The share of crops priced from fresh (not stale) market data today.")}
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.dataHeading")}
        </h2>
        <p>{t("metricsExplanation.dataBody")}</p>
        <p className="text-sm text-gray-400">
          {t("metricsExplanation.disclaimer")}
        </p>
      </section>
    </main>
  );
}
