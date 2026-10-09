import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getLatestPlanBrief,
  getPlanBrief,
  listPlanBriefs,
  runPlanBrief,
} from '../api';
import type {
  PlanBrief,
  PlanBriefDriftRow,
  PlanBriefSummary,
  PlanBriefTrigger,
} from '../types';

const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});
const signedGbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
  signDisplay: 'exceptZero',
});
const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });
const pp = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const errorStatus = (error: unknown): number | undefined =>
  (error as { status?: number } | null)?.status;

type State =
  | { kind: 'loading' }
  | { kind: 'none' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; brief: PlanBrief };

const OUT_OF_BAND = new Set(['over', 'under']);

function DriftTable({ brief }: { brief: PlanBrief }) {
  const { t } = useTranslation();
  const cell = (row: PlanBriefDriftRow) =>
    OUT_OF_BAND.has(row.status)
      ? 'bg-amber-100 font-medium dark:bg-amber-900/40'
      : '';
  return (
    <table className="mb-3 w-full text-sm">
      <caption className="text-left text-xs text-slate-500 dark:text-slate-400">
        {t('planBrief.driftCaption', { band: brief.drift.tolerance_pct })}
      </caption>
      <thead>
        <tr className="text-left">
          <th className="font-medium">{t('planBrief.class')}</th>
          <th className="text-right font-medium">{t('planBrief.actual')}</th>
          <th className="text-right font-medium">{t('planBrief.target')}</th>
          <th className="text-right font-medium">{t('planBrief.drift')}</th>
          <th className="text-right font-medium">{t('planBrief.driftGbp')}</th>
        </tr>
      </thead>
      <tbody>
        {brief.drift.rows.map((row) => (
          <tr key={row.class} className={cell(row)} data-status={row.status}>
            <td>{row.label}</td>
            <td className="text-right">{pct.format(row.current_pct)}%</td>
            <td className="text-right">
              {row.target_pct == null ? '—' : `${pct.format(row.target_pct)}%`}
            </td>
            <td className="text-right">
              {row.drift_pp == null ? '—' : `${pp.format(row.drift_pp)}pp`}
            </td>
            <td className="text-right">
              {row.drift_gbp == null ? '—' : signedGbp.format(row.drift_gbp)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TriggerList({ triggers }: { triggers: PlanBriefTrigger[] }) {
  const { t } = useTranslation();
  if (!triggers.length) return null;
  return (
    <div className="mb-3">
      <h4 className="font-medium">{t('planBrief.triggers')}</h4>
      <ul className="list-disc pl-5 text-sm">
        {triggers.map((trigger, index) => (
          // Index too: a plan may list the same trigger text twice.
          <li key={`${index}:${trigger.trigger}`}>
            <span
              className={
                trigger.verdict === 'fired'
                  ? 'font-semibold text-red-700 dark:text-red-300'
                  : 'font-semibold'
              }
            >
              {t(`planBrief.verdict.${trigger.verdict}`)}
            </span>
            {': '}
            {trigger.trigger}
            {trigger.reason && (
              <span className="text-slate-600 dark:text-slate-300">
                {' — '}
                {trigger.reason}
              </span>
            )}
            {trigger.evidence.length > 0 && (
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                {trigger.evidence
                  .map((e) =>
                    [
                      `${e.tool}${e.field ? `.${e.field}` : ''} = ${String(e.value)}`,
                      e.source,
                      e.as_of,
                    ]
                      .filter(Boolean)
                      .join(', ')
                  )
                  .join('; ')}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function BriefBody({ brief }: { brief: PlanBrief }) {
  const { t } = useTranslation();
  const idleCash = brief.cash.filter((row) => row.days_uninvested != null);
  return (
    <>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('planBrief.asOf', { date: brief.as_of })} ·{' '}
        {t('planBrief.total', {
          value: gbp.format(brief.drift.total_value_gbp),
        })}
      </p>
      {brief.review.due && (
        <p className="mb-2 rounded bg-amber-100 px-2 py-1 text-sm text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
          {t('planBrief.reviewDue', { date: brief.review.next_review })}
        </p>
      )}
      <p className="mb-3 text-sm">{brief.prose}</p>
      <DriftTable brief={brief} />
      {brief.drift.rebalance_targets_match === false && (
        <p className="mb-2 text-xs text-amber-700 dark:text-amber-300">
          {t('planBrief.targetsDiffer')}
        </p>
      )}
      <TriggerList triggers={brief.triggers} />
      {idleCash.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-sm">
          {idleCash.map((row) => (
            <li key={row.account_id}>
              {t('planBrief.idleCash', {
                account: row.account,
                amount: gbp.format(row.cash_gbp),
                days: row.days_uninvested,
              })}
            </li>
          ))}
        </ul>
      )}
      {brief.stale_evidence.length > 0 && (
        <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
          {t('planBrief.staleEvidence', {
            items: brief.stale_evidence
              .map((e) => `${e.metric} (${e.as_of})`)
              .join(', '),
          })}
        </p>
      )}
      <p className="text-xs italic text-slate-500 dark:text-slate-400">
        {brief.disclaimer}
      </p>
    </>
  );
}

function EarlierBriefs({
  owner,
  currentId,
  onPick,
}: {
  owner: string;
  currentId: string;
  onPick: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [briefs, setBriefs] = useState<PlanBriefSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || briefs) return;
    listPlanBriefs(owner)
      .then((res) => setBriefs(res.briefs))
      .catch((err) => setError(errorText(err)));
  }, [open, briefs, owner]);

  return (
    <div className="mt-2 text-sm">
      <button
        type="button"
        className="underline"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {t('planBrief.earlier')}
      </button>
      {open && error && <p className="text-red-600">{error}</p>}
      {open && briefs && (
        <ul className="mt-1 pl-1">
          {briefs.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                className={b.id === currentId ? 'font-semibold' : 'underline'}
                onClick={() => onPick(b.id)}
              >
                {b.as_of}
              </button>{' '}
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {/* HH:MM UTC tells apart briefs run on the same day. */}
                {b.generated_at && `${b.generated_at.slice(11, 16)} UTC · `}
                {t('planBrief.summaryLine', {
                  outside: b.out_of_band.length,
                  fired: b.triggers_fired,
                })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Load the latest (or a chosen) brief and run a new one on demand. */
function usePlanBrief(owner: string) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  // Bumped after each run so the earlier-briefs list re-fetches.
  const [runs, setRuns] = useState(0);

  const load = useCallback(
    async (id?: string) => {
      try {
        const brief = id
          ? await getPlanBrief(owner, id)
          : await getLatestPlanBrief(owner);
        setState({ kind: 'ready', brief });
      } catch (err) {
        setState(
          errorStatus(err) === 404
            ? { kind: 'none' }
            : { kind: 'error', message: errorText(err) }
        );
      }
    },
    [owner]
  );

  useEffect(() => {
    setState({ kind: 'loading' });
    setRunError(null);
    void load(); // errors are captured into state inside load
  }, [load]);

  const run = async () => {
    setRunning(true);
    setRunError(null);
    try {
      setState({ kind: 'ready', brief: await runPlanBrief(owner) });
      setRuns((n) => n + 1);
    } catch (err) {
      setRunError(errorText(err));
    } finally {
      setRunning(false);
    }
  };

  return { state, load, run, running, runError, runs };
}

/**
 * The latest plan-drift brief (#10475): actual vs plan target, review
 * triggers, uninvested cash and whether the review is due. Facts and
 * arithmetic only; it never recommends a trade.
 */
export default function PlanBriefCard({ owner }: { owner: string }) {
  const { t } = useTranslation();
  const { state, load, run, running, runError, runs } = usePlanBrief(owner);

  return (
    <section
      className="mb-4 rounded border p-3"
      aria-label={t('planBrief.title')}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg">{t('planBrief.title')}</h3>
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900 disabled:opacity-60"
        >
          {running ? t('planBrief.running') : t('planBrief.runNow')}
        </button>
      </div>
      {runError && (
        <p className="mb-2 break-words text-sm text-red-600">
          {t('planBrief.runError', { message: runError })}
        </p>
      )}
      {state.kind === 'loading' && (
        <p className="text-sm text-slate-500">{t('planBrief.loading')}</p>
      )}
      {state.kind === 'none' && (
        <p className="text-sm text-slate-500">{t('planBrief.none')}</p>
      )}
      {state.kind === 'error' && (
        <p className="break-words text-sm text-red-600">
          {t('planBrief.loadError', { message: state.message })}
        </p>
      )}
      {state.kind === 'ready' && (
        <>
          <BriefBody brief={state.brief} />
          <EarlierBriefs
            key={`${owner}:${runs}`}
            owner={owner}
            currentId={state.brief.id}
            onPick={(id) => void load(id)}
          />
        </>
      )}
    </section>
  );
}
