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
        <p className="rounded border border-yellow-500 bg-yellow-950/40 p-4 text-sm text-yellow-200">
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

      <section className="space-y-4">
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

      <section className="space-y-4">
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

      <section className="space-y-4">
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
