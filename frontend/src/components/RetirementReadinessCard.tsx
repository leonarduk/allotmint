import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  getRetirementReadinessHistory,
  getRetirementReadinessLatest,
  runRetirementReadiness,
  type RetirementReadinessReport,
  type RetirementReadinessTrendPoint,
} from '../api';

// Retirement readiness monitor (#10484): the stored report's historical
// drawdown figures, their trend across runs, and a "Run now" button. It only
// shows the backend's deterministic figures -- it computes nothing itself.

function errorStatus(err: unknown): number | undefined {
  const status = (err as { status?: unknown } | null)?.status;
  return typeof status === 'number' ? status : undefined;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function RetirementReadinessCard({ owner }: { owner: string }) {
  const { t } = useTranslation();
  const [report, setReport] = useState<RetirementReadinessReport | null>(null);
  const [trend, setTrend] = useState<RetirementReadinessTrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const money = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: 'GBP',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    []
  );

  const load = useCallback(async () => {
    if (!owner) return;
    setError(null);
    try {
      const [latest, history] = await Promise.all([
        getRetirementReadinessLatest(owner),
        getRetirementReadinessHistory(owner),
      ]);
      setReport(latest);
      setTrend(history.trend);
    } catch (err) {
      setReport(null);
      setTrend([]);
      // 404 = no report stored yet; the card offers "Run now" instead.
      if (errorStatus(err) !== 404) setError(errorMessage(err));
    }
  }, [owner]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      await runRetirementReadiness(owner);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  const simulation = report?.results.simulation;
  const chartData = trend.filter(
    (point) => point.sustainable_income_gbp != null
  );

  return (
    <section
      aria-labelledby="retirement-readiness-heading"
      className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
      data-testid="retirement-readiness-card"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2
            id="retirement-readiness-heading"
            className="text-2xl font-semibold text-slate-900"
          >
            {t(
              'retirementReadiness.heading',
              'Retirement readiness: historical drawdown test'
            )}
          </h2>
          <p className="text-sm text-slate-600">
            {t(
              'retirementReadiness.description',
              "The projected pot replayed through every historical sequence of returns since 1871, in today's money."
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={running || !owner}
          className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-60"
        >
          {running
            ? t('retirementReadiness.running', 'Running…')
            : t('retirementReadiness.runNow', 'Run now')}
        </button>
      </header>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {!report && !error && (
        <p className="text-sm text-slate-600">
          {t(
            'retirementReadiness.empty',
            'No readiness report yet. Run it to replay the historical windows.'
          )}
        </p>
      )}
      {report && simulation && (
        <>
          <p className="text-xs text-slate-500">
            {t('retirementReadiness.runDate', 'Last run {{date}}', {
              date: report.run_date,
            })}
          </p>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-slate-600">
                <th className="py-1 pr-4 font-medium">
                  {t('retirementReadiness.survival', 'Windows survived')}
                </th>
                <th className="py-1 text-right font-medium">
                  {t(
                    'retirementReadiness.income',
                    'Highest real income a year'
                  )}
                </th>
              </tr>
            </thead>
            <tbody>
              {simulation.sustainable_income.map((level) => (
                <tr key={level.survival_pct}>
                  <td className="py-1 pr-4">{level.survival_pct}%</td>
                  <td className="py-1 text-right font-semibold">
                    {money.format(level.income_gbp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="space-y-1 text-sm text-slate-700">
            {(['worst', 'median', 'best'] as const).map((name) => {
              const row = simulation[name];
              if (!row) return null;
              return (
                <li key={name}>
                  {t(`retirementReadiness.window.${name}`, `${name} window`)}:{' '}
                  {row.start_year}–{row.end_year},{' '}
                  {money.format(row.sustainable_income_gbp)}
                </li>
              );
            })}
            <li>
              {t(
                'retirementReadiness.windowsCount',
                '{{count}} windows of {{years}} years',
                {
                  count: simulation.windows.count,
                  years: simulation.horizon_years,
                }
              )}
            </li>
          </ul>
          {report.attribution && (
            <p
              className="text-sm text-slate-700"
              data-testid="retirement-readiness-attribution"
            >
              {t('retirementReadiness.change', 'Since {{date}}: {{change}}', {
                date: report.attribution.previous_run_date,
                change: money.format(report.attribution.change_gbp),
              })}{' '}
              ({t('retirementReadiness.contributions', 'contributions')}{' '}
              {money.format(report.attribution.parts_gbp.contributions)},{' '}
              {t('retirementReadiness.markets', 'markets')}{' '}
              {money.format(report.attribution.parts_gbp.markets)},{' '}
              {t('retirementReadiness.assumptions', 'assumptions')}{' '}
              {money.format(report.attribution.parts_gbp.assumptions)}
              {report.attribution.parts_gbp.data_revision !== 0 && (
                <>
                  , {t('retirementReadiness.dataRevision', 'data revisions')}{' '}
                  {money.format(report.attribution.parts_gbp.data_revision)}
                </>
              )}
              )
            </p>
          )}
          {chartData.length > 1 && (
            <div className="h-56" data-testid="retirement-readiness-trend">
              <ResponsiveContainer
                width="100%"
                height="100%"
                minWidth={1}
                minHeight={1}
              >
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="run_date" />
                  <YAxis />
                  <Tooltip formatter={(value) => money.format(Number(value))} />
                  <Line
                    type="monotone"
                    dataKey="sustainable_income_gbp"
                    stroke="#2563eb"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          {[
            ...report.market.flags,
            ...report.assumption_changes.map((c) => c.label),
          ].length > 0 && (
            <ul
              className="list-disc space-y-1 pl-5 text-sm text-amber-800"
              aria-label="flags"
            >
              {report.market.flags.map((flag) => (
                <li key={flag}>{flag}</li>
              ))}
              {report.assumption_changes.map((change) => (
                <li key={change.label}>
                  {t(
                    'retirementReadiness.changed',
                    'Changed since the last run: {{label}}',
                    {
                      label: change.label,
                    }
                  )}
                </li>
              ))}
            </ul>
          )}
          {/* The template narrative repeats the figures and caveats shown here; only a model summary adds anything. */}
          {report.narrative.source === 'llm' && (
            <p
              className="whitespace-pre-line text-sm text-slate-700"
              data-testid="retirement-readiness-narrative"
            >
              {report.narrative.text}
            </p>
          )}
          {report.results.data_notes.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
              {report.results.data_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          <ul className="space-y-1 text-xs text-slate-500" aria-label="caveats">
            {report.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
