// Stress test for the strategy page (#9824): replay one historical event
// against every strategy, beside the owner's current portfolio, to help
// choose a strategy. Opens preselected from /strategy?stress_event=&horizons=.
// The scenario page reuses it without the Apply buttons (no strategy data).
// Events can be filtered by the risk factors they exercised and every matching
// event run in one go for a side-by-side view of the portfolio (#10575).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { applyStrategy, getEvents, runStrategyStress } from '../api';
import type {
  ScenarioEvent,
  StrategyList,
  StrategyStressHorizon,
  StrategyStressResult,
  StrategyStressRow,
} from '../types';
import { allocationKeyLabel } from '../lib/assetClass';
import { confirmApply } from '../lib/strategyApply';

const STRESS_HORIZONS = ['1d', '1w', '1m', '3m', '1y'];
/** Display order of the factor chips; matches RISK_FACTORS in backend/routes/events.py. */
const RISK_FACTORS = [
  'equity',
  'rates',
  'inflation',
  'fx',
  'credit',
  'liquidity',
  'commodities',
  'volatility',
];
const DEFAULT_HORIZONS = ['1m', '3m', '1y'];

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

const pct = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
});

/** Horizons from the URL, in display order; the defaults when none are valid. */
function initialHorizons(raw: string | null): string[] {
  const wanted = new Set((raw ?? '').split(',').map((h) => h.trim()));
  const picked = STRESS_HORIZONS.filter((h) => wanted.has(h));
  return picked.length ? picked : DEFAULT_HORIZONS;
}

/** Events tagged with every selected factor; all events when none are selected. */
function matchingEvents(events: ScenarioEvent[], factors: string[]) {
  return events.filter((ev) =>
    factors.every((f) => ev.risk_factors?.includes(f))
  );
}

function useEvents() {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    getEvents()
      .then((list) => {
        if (!cancelled) setEvents(Array.isArray(list) ? list : []);
      })
      .catch((err) => {
        if (!cancelled) setError(errorText(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return { events, error };
}

function ReturnCell({ value }: { value: StrategyStressHorizon | undefined }) {
  const { t } = useTranslation();
  if (!value || value.return_pct == null) {
    const missing = missingLabels(value?.missing ?? []);
    return (
      <td
        className="px-2 py-1 text-right text-slate-500 dark:text-slate-400"
        title={
          missing ? t('strategyStress.missingTitle', { missing }) : undefined
        }
      >
        {t('strategyStress.noData')}
      </td>
    );
  }
  const tone =
    value.return_pct < 0
      ? 'text-red-600 dark:text-red-400'
      : 'text-green-700 dark:text-green-400';
  const partial = value.coverage_pct != null && value.coverage_pct < 100;
  return (
    <td className={`px-2 py-1 text-right ${tone}`}>
      {pct.format(value.return_pct)}%
      {value.return_basis === 'price' && (
        <span title={t('strategyStress.priceOnlyTitle')}>†</span>
      )}
      {partial && (
        <span className="block text-xs text-slate-500 dark:text-slate-400">
          {t('strategyStress.priced', { pct: value.coverage_pct?.toFixed(0) })}
        </span>
      )}
    </td>
  );
}

/** Asset-class labels, alphabetical, comma-separated. */
function missingLabels(keys: string[]): string {
  return keys
    .map(allocationKeyLabel)
    .sort((a, b) => a.localeCompare(b))
    .join(', ');
}

/** Asset classes missing data at any horizon, listed once per row. */
function rowMissing(row: StrategyStressRow): string {
  const keys = new Set(
    Object.values(row.horizons).flatMap((h) => h.missing ?? [])
  );
  return missingLabels([...keys]);
}

/** True when neither the portfolio nor any strategy has a single figure. */
function nothingCovered(result: StrategyStressResult): boolean {
  const rows = [
    ...(result.portfolio ? [result.portfolio.horizons] : []),
    ...result.strategies.map((row) => row.horizons),
  ];
  return rows.every((horizons) =>
    Object.values(horizons).every((h) => h.return_pct == null)
  );
}

function seriesLine(row: StrategyStressRow): string {
  return Object.entries(row.series)
    .filter(([, series]) => series.length > 0)
    .map(
      ([sleeve, series]) =>
        `${allocationKeyLabel(sleeve)}: ${series.join(', ')}`
    )
    .join(' · ');
}

/** Rows sorted best-first by one horizon; rows with no number go last. */
function sortRows(rows: StrategyStressRow[], horizon: string | null) {
  if (!horizon) return rows;
  const value = (row: StrategyStressRow) =>
    row.horizons[horizon]?.return_pct ?? Number.NEGATIVE_INFINITY;
  return [...rows].sort((a, b) => value(b) - value(a));
}

function ResultTable({
  result,
  busy,
  onApply,
}: {
  result: StrategyStressResult;
  busy: boolean;
  /** Omitted where strategies cannot be applied; hides the Apply column. */
  onApply?: (row: StrategyStressRow) => void;
}) {
  const { t } = useTranslation();
  const [sortBy, setSortBy] = useState<string | null>(null);
  const rows = useMemo(
    () => sortRows(result.strategies, sortBy),
    [result.strategies, sortBy]
  );
  if (nothingCovered(result)) {
    return (
      <p className="text-sm text-amber-700 dark:text-amber-300" role="note">
        {t('strategyStress.nothingCovered', { date: result.event.date })}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left">
              {t('strategyStress.col.strategy')}
            </th>
            {result.horizons.map((h) => (
              <th key={h} className="px-2 py-1 text-right">
                <button
                  type="button"
                  className="underline decoration-dotted"
                  onClick={() => setSortBy(h)}
                  aria-label={t('strategyStress.sortBy', { horizon: h })}
                >
                  {h}
                  {sortBy === h ? ' ▼' : ''}
                </button>
              </th>
            ))}
            {onApply && (
              <th
                className="px-2 py-1"
                aria-label={t('strategyStress.col.actions')}
              />
            )}
          </tr>
        </thead>
        <tbody>
          {result.portfolio && (
            <tr className="border-t bg-slate-50 font-medium dark:bg-slate-800">
              <td className="px-2 py-1">{t('strategyStress.portfolio')}</td>
              {result.horizons.map((h) => (
                <ReturnCell key={h} value={result.portfolio?.horizons[h]} />
              ))}
              {onApply && <td />}
            </tr>
          )}
          {rows.map((row) => (
            <tr key={row.id} className="border-t">
              <td className="px-2 py-1">
                {row.name}
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  {seriesLine(row)}
                </span>
                {rowMissing(row) && (
                  <span className="block text-xs text-amber-700 dark:text-amber-300">
                    {t('strategyStress.rowMissing', {
                      missing: rowMissing(row),
                    })}
                  </span>
                )}
              </td>
              {result.horizons.map((h) => (
                <ReturnCell key={h} value={row.horizons[h]} />
              ))}
              {onApply && (
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onApply(row)}
                    aria-label={t('strategyLibrary.row.applyAria', {
                      name: row.name,
                    })}
                    className="rounded bg-blue-500 px-2 py-1 text-white disabled:opacity-50"
                  >
                    {t('strategyLibrary.row.apply')}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategyStress.footnote')} {result.disclaimer}
      </p>
    </div>
  );
}

function FactorChips({
  events,
  selected,
  onToggle,
  onClear,
}: {
  events: ScenarioEvent[];
  selected: string[];
  onToggle: (factor: string) => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  const tagged = new Set(events.flatMap((ev) => ev.risk_factors ?? []));
  const factors = RISK_FACTORS.filter((f) => tagged.has(f));
  if (!factors.length) return null;
  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-2"
      role="group"
      aria-label={t('strategyStress.factors')}
    >
      <span className="text-sm">{t('strategyStress.factors')}:</span>
      {factors.map((f) => {
        const on = selected.includes(f);
        return (
          <button
            key={f}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(f)}
            className={`rounded-full border px-3 py-0.5 text-sm ${
              on
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            {t(`strategyStress.factor.${f}`)}
          </button>
        );
      })}
      {selected.length > 0 && (
        <button type="button" className="text-sm underline" onClick={onClear}>
          {t('strategyStress.clearFactors')}
        </button>
      )}
      <span className="text-xs text-slate-500 dark:text-slate-400">
        {t('strategyStress.factorsHelp')}
      </span>
    </div>
  );
}

function useFactorLabels() {
  const { t } = useTranslation();
  return useCallback(
    (ev: ScenarioEvent) =>
      (ev.risk_factors ?? [])
        .map((f) => t(`strategyStress.factor.${f}`))
        .join(', '),
    [t]
  );
}

type BatchRow = {
  event: ScenarioEvent;
  result: StrategyStressResult | null;
  error: string | null;
};

type Batch = { horizons: string[]; rows: BatchRow[]; total: number };

/** Runs events one after another; a failed event becomes an error row. */
function useBatchRun(owner: string) {
  const [batch, setBatch] = useState<Batch | null>(null);
  // Bumped per run and on unmount so a superseded loop stops writing state.
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current += 1;
    },
    []
  );
  const run = useCallback(
    async (events: ScenarioEvent[], horizons: string[]) => {
      generation.current += 1;
      const gen = generation.current;
      const rows: BatchRow[] = [];
      setBatch({ horizons, rows: [], total: events.length });
      for (const event of events) {
        let row: BatchRow;
        try {
          const result = await runStrategyStress(owner, {
            event_id: event.id,
            horizons,
          });
          row = { event, result, error: null };
        } catch (err) {
          row = { event, result: null, error: errorText(err) };
        }
        if (gen !== generation.current) return;
        rows.push(row);
        setBatch({ horizons, rows: [...rows], total: events.length });
      }
    },
    [owner]
  );
  const running = batch != null && batch.rows.length < batch.total;
  return { batch, running, run };
}

function BatchTable({
  batch,
  onDetails,
}: {
  batch: Batch;
  onDetails: (eventId: string) => void;
}) {
  const { t } = useTranslation();
  const factorLabels = useFactorLabels();
  return (
    <div className="mb-4 overflow-x-auto">
      <h3 className="mb-1 text-lg">{t('strategyStress.batchTitle')}</h3>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left">
              {t('strategyStress.col.event')}
            </th>
            {batch.horizons.map((h) => (
              <th key={h} className="px-2 py-1 text-right">
                {h}
              </th>
            ))}
            <th
              className="px-2 py-1"
              aria-label={t('strategyStress.col.actions')}
            />
          </tr>
        </thead>
        <tbody>
          {batch.rows.map(({ event, result, error }) => (
            <tr key={event.id} className="border-t">
              <td className="px-2 py-1">
                {event.name}
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  {factorLabels(event)}
                </span>
              </td>
              {error ? (
                <td
                  colSpan={batch.horizons.length}
                  className="break-words px-2 py-1 text-red-600"
                >
                  {error}
                </td>
              ) : (
                batch.horizons.map((h) => (
                  <ReturnCell key={h} value={result?.portfolio?.horizons[h]} />
                ))
              )}
              <td className="px-2 py-1 text-right">
                <button
                  type="button"
                  className="rounded border px-2 py-0.5 text-xs"
                  onClick={() => onDetails(event.id)}
                  aria-label={t('strategyStress.detailsAria', {
                    name: event.name,
                  })}
                >
                  {t('strategyStress.details')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategyStress.batchFootnote')}
      </p>
    </div>
  );
}

function useStressRun(owner: string) {
  const [result, setResult] = useState<StrategyStressResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (request: {
      event_id?: string;
      date?: string;
      horizons: string[];
    }) => {
      setLoading(true);
      setError(null);
      try {
        setResult(await runStrategyStress(owner, request));
      } catch (err) {
        setResult(null);
        setError(errorText(err));
      } finally {
        setLoading(false);
      }
    },
    [owner]
  );
  return { result, loading, error, run };
}

export default function StrategyStressPanel({
  owner,
  data,
  hasTargets,
  onChanged,
}: {
  owner: string;
  /** Strategy data, targets flag and reload hook enable the Apply buttons. */
  data?: StrategyList;
  hasTargets?: boolean;
  /** Reload strategies and the plan after a strategy is applied. */
  onChanged?: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { events, error: eventsError } = useEvents();
  const [eventId, setEventId] = useState(params.get('stress_event') ?? '');
  const [date, setDate] = useState('');
  const [horizons, setHorizons] = useState(() =>
    initialHorizons(params.get('horizons'))
  );
  const { result, loading, error, run } = useStressRun(owner);
  const [factors, setFactors] = useState<string[]>([]);
  const shown = useMemo(
    () => matchingEvents(events, factors),
    [events, factors]
  );
  const factorLabels = useFactorLabels();
  const { batch, running: batchRunning, run: runBatch } = useBatchRun(owner);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [autoRan, setAutoRan] = useState(false);

  const request = useMemo(
    () => (eventId ? { event_id: eventId, horizons } : { date, horizons }),
    [eventId, date, horizons]
  );
  const canRun = Boolean(owner) && (eventId || date) && horizons.length > 0;
  const canRunAll =
    Boolean(owner) && shown.length > 0 && horizons.length > 0 && !batchRunning;

  function setFactorFilter(next: string[]) {
    setFactors(next);
    // Drop a selected event the new filter hides, so the dropdown matches it.
    if (
      eventId &&
      !matchingEvents(events, next).some((ev) => ev.id === eventId)
    )
      setEventId('');
  }

  const toggleFactor = (f: string) =>
    setFactorFilter(
      factors.includes(f) ? factors.filter((x) => x !== f) : [...factors, f]
    );

  function showDetails(id: string) {
    setEventId(id);
    void run({ event_id: id, horizons: batch?.horizons ?? horizons });
  }

  // A link from the scenario page runs the preselected event straight away.
  useEffect(() => {
    if (autoRan || !owner || !params.get('stress_event')) return;
    setAutoRan(true);
    void run(request); // errors are captured into state inside run
  }, [autoRan, owner, params, request, run]);

  const toggleHorizon = (h: string) =>
    setHorizons((current) =>
      current.includes(h)
        ? current.filter((x) => x !== h)
        : STRESS_HORIZONS.filter((x) => x === h || current.includes(x))
    );

  async function handleApply(row: StrategyStressRow) {
    if (!data || !onChanged) return;
    if (!confirmApply(data, hasTargets ?? false, row.name, t)) return;
    setBusy(true);
    setNotice(null);
    setApplyError(null);
    try {
      await applyStrategy(owner, row.id);
      await onChanged();
      setNotice(t('strategyLibrary.applied', { name: row.name }));
    } catch (err) {
      setApplyError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-6" aria-label={t('strategyStress.title')}>
      <h2 className="mb-2 text-xl">{t('strategyStress.title')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategyStress.help')}
      </p>
      <FactorChips
        events={events}
        selected={factors}
        onToggle={toggleFactor}
        onClear={() => setFactorFilter([])}
      />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select
          aria-label={t('strategyStress.event')}
          className="rounded border p-1"
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
        >
          <option value="">{t('strategyStress.customDate')}</option>
          {shown.map((ev) => (
            <option key={ev.id} value={ev.id}>
              {ev.risk_factors?.length
                ? `${ev.name} [${factorLabels(ev)}]`
                : ev.name}
            </option>
          ))}
        </select>
        {!eventId && (
          <input
            type="date"
            aria-label={t('strategyStress.date')}
            className="rounded border p-1"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        )}
        {STRESS_HORIZONS.map((h) => (
          <label key={h} className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={horizons.includes(h)}
              onChange={() => toggleHorizon(h)}
            />
            {h}
          </label>
        ))}
        <button
          type="button"
          disabled={!canRun || loading}
          onClick={() => void run(request)}
          className="rounded bg-blue-500 px-4 py-1 text-white disabled:opacity-50"
        >
          {loading ? t('strategyStress.running') : t('strategyStress.run')}
        </button>
        <button
          type="button"
          disabled={!canRunAll}
          onClick={() => void runBatch(shown, horizons)}
          className="rounded border border-blue-500 px-4 py-1 text-blue-600 disabled:opacity-50 dark:text-blue-300"
        >
          {batchRunning && batch
            ? t('strategyStress.runningAll', {
                done: batch.rows.length,
                total: batch.total,
              })
            : t('strategyStress.runAll', { n: shown.length })}
        </button>
      </div>
      {factors.length > 0 && shown.length === 0 && (
        <p
          className="mb-2 text-sm text-amber-700 dark:text-amber-300"
          role="note"
        >
          {t('strategyStress.noMatches')}
        </p>
      )}
      {[eventsError, error, applyError].map(
        (message) =>
          message && (
            <p key={message} className="mb-2 break-words text-sm text-red-600">
              {message}
            </p>
          )
      )}
      {notice && (
        <p
          className="mb-2 text-sm text-green-700 dark:text-green-400"
          role="status"
        >
          {notice}
        </p>
      )}
      {batch && batch.rows.length > 0 && (
        <BatchTable batch={batch} onDetails={showDetails} />
      )}
      {result && (
        <ResultTable
          result={result}
          busy={busy}
          onApply={data && onChanged ? handleApply : undefined}
        />
      )}
    </section>
  );
}
