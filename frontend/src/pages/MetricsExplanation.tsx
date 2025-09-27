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
import { money, percentOrNa } from "../lib/money";
import type {
  AlphaBreakdownPoint,
  AlphaResponse,
  MaxDrawdownPoint,
  MaxDrawdownResponse,
  TrackingErrorPoint,
  TrackingErrorResponse,
} from "../types";

export default function MetricsExplanation() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const group = searchParams.get("group");
  const owner = searchParams.get("owner");
  const benchmark = searchParams.get("benchmark") || "VWRL.L";
  const daysParam = searchParams.get("days");
  const days = daysParam ? Number(daysParam) : 365;
  const target = group ?? owner ?? "all";
  const isGroup = Boolean(group);

  const [alphaData, setAlphaData] = useState<AlphaResponse | null>(null);
  const [trackingData, setTrackingData] = useState<TrackingErrorResponse | null>(
    null,
  );
  const [drawdownData, setDrawdownData] = useState<MaxDrawdownResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const alphaNotesRaw = t("metricsExplanation.sections.alpha.notes", {
    returnObjects: true,
  });
  const trackingErrorNotesRaw = t(
    "metricsExplanation.sections.trackingError.notes",
    { returnObjects: true },
  );
  const drawdownNotesRaw = t(
    "metricsExplanation.sections.maxDrawdown.notes",
    {
      returnObjects: true,
    },
  );
  const alphaNotes = Array.isArray(alphaNotesRaw)
    ? (alphaNotesRaw as string[])
    : [];
  const trackingErrorNotes = Array.isArray(trackingErrorNotesRaw)
    ? (trackingErrorNotesRaw as string[])
    : [];
  const drawdownNotes = Array.isArray(drawdownNotesRaw)
    ? (drawdownNotesRaw as string[])
    : [];

  useEffect(() => {
    if (!target) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const alphaPromise = isGroup
      ? getGroupAlphaVsBenchmark(target, benchmark, days)
      : getAlphaVsBenchmark(target, benchmark, days);
    const trackingPromise = isGroup
      ? getGroupTrackingError(target, benchmark, days)
      : getTrackingError(target, benchmark, days);
    const drawdownPromise = isGroup
      ? getGroupMaxDrawdown(target, days)
      : getMaxDrawdown(target, days);

    Promise.all([alphaPromise, trackingPromise, drawdownPromise])
      .then(([alphaRes, trackingRes, drawdownRes]) => {
        if (cancelled) return;
        setAlphaData(alphaRes);
        setTrackingData(trackingRes);
        setDrawdownData(drawdownRes);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError(String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [benchmark, days, isGroup, target]);

  const backLink = useMemo(() => {
    const params = new URLSearchParams();
    if (group) params.set("group", group);
    else if (owner) params.set("owner", owner);
    if (benchmark) params.set("benchmark", benchmark);
    if (daysParam) params.set("days", daysParam);
    const suffix = params.toString();
    return suffix ? `/?${suffix}` : "/?group=all";
  }, [benchmark, daysParam, group, owner]);

  const alphaBreakdown = (alphaData?.daily_breakdown || []) as AlphaBreakdownPoint[];
  const trackingBreakdown = (trackingData?.daily_active_returns || []) as TrackingErrorPoint[];
  const drawdownPath = (drawdownData?.drawdown_path || []) as MaxDrawdownPoint[];

  const latestAlpha = alphaBreakdown[alphaBreakdown.length - 1];
  const trackingErrorValue =
    trackingData?.tracking_error ?? trackingData?.standard_deviation ?? null;
  const contextLabel = isGroup
    ? t("metricsExplanation.groupLabel", { group: target })
    : t("metricsExplanation.ownerLabel", { owner: target });

  return (
    <main className="container mx-auto max-w-3xl space-y-10 p-4">
      <header className="space-y-2">
        <Link to={backLink} className="inline-block text-blue-500 hover:underline">
          {t("metricsExplanation.backLink")}
        </Link>
        <h1 className="text-3xl font-bold">
          {t("metricsExplanation.title")}
        </h1>
        <p className="text-lg text-gray-300">
          {t("metricsExplanation.intro")}
        </p>
        <p className="text-sm text-gray-400">
          {t("metricsExplanation.context", { context: contextLabel, days })}
        </p>
        {loading && (
          <p className="text-sm text-blue-300">
            {t("metricsExplanation.loading")}
          </p>
        )}
        {error && (
          <p className="text-sm text-red-400">
            {t("metricsExplanation.error", { message: error })}
          </p>
        )}
      </header>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.alpha.title")}
        </h2>
        <p>{t("metricsExplanation.sections.alpha.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.alpha.calculation")}</p>
        <p className="rounded-md bg-slate-800 p-3 text-sm text-slate-200">
          <strong className="font-semibold">Formula:</strong> α = Π<sub>t</sub>(1 +
          r<sub>p,t</sub>) − 1 − [Π<sub>t</sub>(1 + r<sub>b,t</sub>) − 1]
        </p>
        <div className="rounded-md border border-slate-700 p-4">
          <p className="text-sm text-slate-300">
            <strong className="font-semibold">Latest alpha:</strong>{" "}
            {percentOrNa(alphaData?.alpha_vs_benchmark ?? null)} ({
              alphaData?.benchmark
            })
          </p>
          {latestAlpha && (
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              <li>
                Portfolio cumulative return: {percentOrNa(latestAlpha.portfolio_cumulative)}
              </li>
              <li>
                Benchmark cumulative return: {percentOrNa(
                  latestAlpha.benchmark_cumulative,
                )}
              </li>
              <li>Difference (α): {percentOrNa(latestAlpha.alpha)}</li>
            </ul>
          )}
          {alphaBreakdown.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-semibold text-blue-300">
                Daily cumulative path ({alphaBreakdown.length} days)
              </summary>
              <div className="mt-2 max-h-72 overflow-auto rounded-md border border-slate-700">
                <table className="min-w-full divide-y divide-slate-700 text-left text-xs">
                  <thead className="bg-slate-900 text-slate-200">
                    <tr>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">r<sub>p,t</sub></th>
                      <th className="px-3 py-2">r<sub>b,t</sub></th>
                      <th className="px-3 py-2">Π(1 + r<sub>p</sub>) − 1</th>
                      <th className="px-3 py-2">Π(1 + r<sub>b</sub>) − 1</th>
                      <th className="px-3 py-2">α</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {alphaBreakdown.map((row) => (
                      <tr key={row.date} className="odd:bg-slate-900/40">
                        <td className="px-3 py-2 font-mono">{row.date}</td>
                        <td className="px-3 py-2">{percentOrNa(row.portfolio_return)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.benchmark_return)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.portfolio_cumulative)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.benchmark_cumulative)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.alpha)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
        {alphaNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {alphaNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.trackingError.title")}
        </h2>
        <p>{t("metricsExplanation.sections.trackingError.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.trackingError.calculation")}</p>
        <p className="rounded-md bg-slate-800 p-3 text-sm text-slate-200">
          <strong className="font-semibold">Formula:</strong> Tracking Error =
          σ(r<sub>p,t</sub> − r<sub>b,t</sub>) using the sample standard deviation of
          daily active returns.
        </p>
        <div className="rounded-md border border-slate-700 p-4">
          <p className="text-sm text-slate-300">
            <strong className="font-semibold">Standard deviation:</strong>{" "}
            {percentOrNa(trackingErrorValue ?? null)} ({trackingData?.benchmark})
          </p>
          {trackingBreakdown.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-semibold text-blue-300">
                Daily active returns ({trackingBreakdown.length} days)
              </summary>
              <div className="mt-2 max-h-72 overflow-auto rounded-md border border-slate-700">
                <table className="min-w-full divide-y divide-slate-700 text-left text-xs">
                  <thead className="bg-slate-900 text-slate-200">
                    <tr>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">r<sub>p,t</sub></th>
                      <th className="px-3 py-2">r<sub>b,t</sub></th>
                      <th className="px-3 py-2">Active r<sub>t</sub></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {trackingBreakdown.map((row) => (
                      <tr key={row.date} className="odd:bg-slate-900/40">
                        <td className="px-3 py-2 font-mono">{row.date}</td>
                        <td className="px-3 py-2">{percentOrNa(row.portfolio_return)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.benchmark_return)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.active_return)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
        {trackingErrorNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {trackingErrorNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.maxDrawdown.title")}
        </h2>
        <p>{t("metricsExplanation.sections.maxDrawdown.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.maxDrawdown.calculation")}</p>
        <p className="rounded-md bg-slate-800 p-3 text-sm text-slate-200">
          <strong className="font-semibold">Formula:</strong> Drawdown<sub>t</sub> =
          V<sub>t</sub> / max(V<sub>0..t</sub>) − 1. Max drawdown is the minimum drawdown
          across the window.
        </p>
        <div className="rounded-md border border-slate-700 p-4">
          <p className="text-sm text-slate-300">
            <strong className="font-semibold">Max drawdown:</strong>{" "}
            {percentOrNa(drawdownData?.max_drawdown ?? null)}
          </p>
          <div className="mt-2 space-y-1 text-sm text-slate-300">
            {drawdownData?.peak && (
              <p>
                Peak: {drawdownData.peak.date} at {money(drawdownData.peak.value)}
              </p>
            )}
            {drawdownData?.trough && (
              <p>
                Trough: {drawdownData.trough.date} at {money(drawdownData.trough.value)}
              </p>
            )}
            {drawdownData?.peak && drawdownData?.trough && (
              <p>
                Peak → Trough loss: {percentOrNa(drawdownData.max_drawdown ?? null)}
              </p>
            )}
          </div>
          {drawdownPath.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-semibold text-blue-300">
                Running peaks and drawdowns ({drawdownPath.length} days)
              </summary>
              <div className="mt-2 max-h-72 overflow-auto rounded-md border border-slate-700">
                <table className="min-w-full divide-y divide-slate-700 text-left text-xs">
                  <thead className="bg-slate-900 text-slate-200">
                    <tr>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Value</th>
                      <th className="px-3 py-2">Running peak</th>
                      <th className="px-3 py-2">Drawdown</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {drawdownPath.map((row) => (
                      <tr key={row.date} className="odd:bg-slate-900/40">
                        <td className="px-3 py-2 font-mono">{row.date}</td>
                        <td className="px-3 py-2">{money(row.portfolio_value)}</td>
                        <td className="px-3 py-2">{money(row.running_peak)}</td>
                        <td className="px-3 py-2">{percentOrNa(row.drawdown)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
        {drawdownNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {drawdownNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
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
