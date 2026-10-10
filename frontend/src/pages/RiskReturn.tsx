import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import {
  getBenchmarkRiskReturn,
  getGroupRiskReturn,
  getGroups,
  getOwners,
} from '../api';
import type { BenchmarkRiskReturn, GroupSummary, OwnerSummary } from '../types';
import { useFetch } from '../hooks/useFetch';
import {
  PRESET_BENCHMARKS,
  addBenchmark,
  averageLine,
  buildBenchmarkSeries,
  buildPortfolioSeries,
  isIndexSeries,
  normaliseTicker,
  parseRiskFreePct,
  parseStoredBenchmarks,
  plottable,
  removeBenchmark,
  seriesDetails,
  sharpeRatio,
  sideOfAverage,
  type AverageLine,
  type Benchmark,
  type ChartSeries,
} from '../lib/riskReturn';
import { DEFAULT_GROUP_SLUG } from '../utils/groups';
import { createOwnerDisplayLookup, sanitizeOwners } from '../utils/owners';

const WINDOWS = [
  { key: '1y', days: 365 },
  { key: '3y', days: 365 * 3 },
  { key: '5y', days: 365 * 5 },
] as const;

const BENCHMARKS_KEY = 'riskReturn.benchmarks';
const HIDDEN_KEY = 'riskReturn.hidden';
const SHOW_AVERAGE_KEY = 'riskReturn.showAverage';
const RISK_FREE_KEY = 'riskReturn.riskFreePct';
// Below three years a Sharpe ratio's standard error is large (about +/-1 at
// one year), so differences between points are mostly noise.
const RELIABLE_WINDOW_DAYS = 365 * 3;

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage blocked (private window, quota): the choice lasts this visit only.
  }
}

function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Storage blocked: nothing was stored to remove.
  }
}

function readHidden(): Set<string> {
  try {
    const parsed: unknown = JSON.parse(readStorage(HIDDEN_KEY) ?? '[]');
    return new Set(
      Array.isArray(parsed)
        ? parsed.filter((v): v is string => typeof v === 'string')
        : []
    );
  } catch {
    return new Set();
  }
}

type BenchmarkState = Record<string, BenchmarkRiskReturn | null>;

/**
 * Per-ticker benchmark results for the window ``days``: a ticker is
 * ``undefined`` while loading, ``null`` when unavailable. Results are kept
 * per ``days:ticker`` so adding a ticker fetches only that one, and
 * switching window and back reuses what was already fetched. A failed
 * ticker is retried the next time the list or window changes (e.g. removing
 * and re-adding it).
 */
function useBenchmarkResults(benchmarks: Benchmark[], days: number) {
  const [results, setResults] = useState<BenchmarkState>({});
  const requested = useRef(new Set<string>());

  useEffect(() => {
    for (const { ticker } of benchmarks) {
      const key = `${days}:${ticker}`;
      if (requested.current.has(key)) continue;
      requested.current.add(key);
      setResults(({ [key]: _stale, ...rest }) => rest);
      getBenchmarkRiskReturn(ticker, days)
        .then((res) => setResults((prev) => ({ ...prev, [key]: res })))
        .catch(() => {
          requested.current.delete(key);
          setResults((prev) => ({ ...prev, [key]: null }));
        });
    }
  }, [benchmarks, days]);

  return useMemo(
    () =>
      Object.fromEntries(
        benchmarks.map(({ ticker }) => [ticker, results[`${days}:${ticker}`]])
      ) as Record<string, BenchmarkRiskReturn | null | undefined>,
    [benchmarks, days, results]
  );
}

function formatPct(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}%`;
}

function formatRatio(value: number | null): string {
  return value == null ? '—' : value.toFixed(2);
}

interface TooltipEntry {
  payload?: {
    label: string;
    x: number;
    y: number;
    name?: string | null;
    sector?: string | null;
    basis?: string | null;
    sharpeReturn?: number | null;
    isAverage?: boolean;
  };
}

function PointTooltip({
  active,
  payload,
  returnLabel,
  volatilityLabel,
  sharpeLabel,
  riskFreePct,
  average,
  sideLabels,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  returnLabel: string;
  volatilityLabel: string;
  sharpeLabel: string;
  riskFreePct: number;
  average: AverageLine | null;
  sideLabels: Record<'above' | 'below' | 'on', string>;
}) {
  const point = active ? payload?.[0]?.payload : undefined;
  if (!point) return null;
  const side =
    average && !point.isAverage
      ? sideOfAverage(average, point.x, point.y)
      : null;
  return (
    <div
      style={{
        // Theme tokens from index.css, defined for light and dark, so the
        // text never inherits a light colour onto a light background.
        background: 'var(--surface-card-bg)',
        color: 'var(--surface-card-color)',
        border: '1px solid var(--surface-card-border)',
        padding: '0.5rem',
        borderRadius: 4,
      }}
    >
      <strong>{point.label}</strong>
      {point.name && <div>{point.name}</div>}
      {point.sector && <div>{point.sector}</div>}
      <div>
        {returnLabel}: {formatPct(point.y)}
      </div>
      <div>
        {volatilityLabel}: {formatPct(point.x)}
      </div>
      <div>
        {sharpeLabel}:{' '}
        {formatRatio(
          // Series use the reports' trading-day basis and show "—" without
          // it rather than a figure on another basis; the average marker's
          // Sharpe is the line's slope, from its plotted return.
          sharpeRatio(
            point.x,
            point.isAverage ? point.y : point.sharpeReturn,
            riskFreePct
          )
        )}
      </div>
      {point.basis && <div>{point.basis}</div>}
      {side && <div>{sideLabels[side]}</div>}
    </div>
  );
}

function SeriesToggle({
  series,
  hidden,
  onToggle,
  onRemove,
  unavailableLabel,
  removeLabel,
  indexLabel,
  basisLabel,
}: {
  series: ChartSeries;
  hidden: boolean;
  onToggle: () => void;
  onRemove?: () => void;
  unavailableLabel: string | null;
  removeLabel: string;
  indexLabel: string;
  basisLabel: string;
}) {
  const { name, sector } = seriesDetails(series, indexLabel);
  const basis = isIndexSeries(series) ? basisLabel : null;
  const hoverText = [series.label, name, sector, basis]
    .filter(Boolean)
    .join('\n');
  return (
    <li style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
      <label
        title={hoverText}
        style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}
      >
        <input type="checkbox" checked={!hidden} onChange={onToggle} />
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: 12,
            height: 12,
            background: series.color,
            borderRadius: series.kind === 'benchmark' ? 0 : '50%',
            transform:
              series.kind === 'benchmark' ? 'rotate(45deg)' : undefined,
          }}
        />
        {series.label}
        {unavailableLabel && (
          <em style={{ opacity: 0.7 }}> ({unavailableLabel})</em>
        )}
      </label>
      {basis && (
        <small style={{ opacity: 0.7 }} aria-hidden="true">
          {basis}
        </small>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`${removeLabel} ${series.label}`}
          title={removeLabel}
        >
          ×
        </button>
      )}
    </li>
  );
}

export default function RiskReturn() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(365);
  const [group, setGroup] = useState<string>(DEFAULT_GROUP_SLUG);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>(() =>
    parseStoredBenchmarks(readStorage(BENCHMARKS_KEY))
  );
  const [hidden, setHidden] = useState<Set<string>>(readHidden);
  const [showAverage, setShowAverage] = useState<boolean>(
    () => readStorage(SHOW_AVERAGE_KEY) !== 'false'
  );
  // The user's own risk-free rate (percent); null follows the configured one.
  const [riskFreeInput, setRiskFreeInput] = useState<string | null>(() =>
    readStorage(RISK_FREE_KEY)
  );
  const [tickerInput, setTickerInput] = useState('');
  const [tickerError, setTickerError] = useState<string | null>(null);

  const groups = useFetch<GroupSummary[]>(getGroups, []);
  const owners = useFetch<OwnerSummary[]>(getOwners, []);
  const fetchPoints = useCallback(
    () => getGroupRiskReturn(group, days),
    [group, days]
  );
  const points = useFetch(fetchPoints, [fetchPoints]);
  const benchmarkResults = useBenchmarkResults(benchmarks, days);

  useEffect(
    () => writeStorage(BENCHMARKS_KEY, JSON.stringify(benchmarks)),
    [benchmarks]
  );
  useEffect(
    () => writeStorage(SHOW_AVERAGE_KEY, String(showAverage)),
    [showAverage]
  );
  useEffect(
    () => writeStorage(HIDDEN_KEY, JSON.stringify([...hidden])),
    [hidden]
  );

  const ownerNames = useMemo(
    () => createOwnerDisplayLookup(sanitizeOwners(owners.data ?? [])),
    [owners.data]
  );
  const portfolioSeries = useMemo(
    () =>
      buildPortfolioSeries(points.data, {
        days,
        ownerNames,
        groupLabel: t('riskReturn.entirePortfolio'),
        ownerTotalLabel: (owner) => t('riskReturn.ownerTotal', { owner }),
      }),
    [points.data, days, ownerNames, t]
  );
  const benchmarkSeries = useMemo(
    () =>
      buildBenchmarkSeries(
        benchmarks,
        benchmarkResults,
        days,
        portfolioSeries.length
      ),
    [benchmarks, benchmarkResults, days, portfolioSeries.length]
  );
  const visible = [...portfolioSeries, ...benchmarkSeries].filter(
    (s) => !hidden.has(s.id) && plottable(s)
  );
  const configuredRiskFreePct = Number(
    ((points.data?.risk_free_rate ?? 0) * 100).toFixed(2)
  );
  // Blank until the configured rate has loaded, rather than showing 0.
  const riskFreeText =
    riskFreeInput ?? (points.data ? String(configuredRiskFreePct) : '');
  const typedRiskFreePct = parseRiskFreePct(riskFreeInput);
  const riskFreePct = typedRiskFreePct ?? configuredRiskFreePct;
  // A typed rate that can't be used falls back to the configured one; say so
  // rather than plot at a rate the box doesn't show. A cleared box just means
  // "use the configured rate", which the placeholder shows.
  const riskFreeFallback = !!riskFreeInput?.trim() && typedRiskFreePct == null;
  // Benchmarks often load before the group's configured rate, so wait for
  // the rate rather than draw the line at 0% and then move it.
  const riskFreeKnown = typedRiskFreePct != null || points.data != null;
  // Averaged over what is on the chart, so ticking series in or out
  // changes what "average" means (e.g. only accounts, or with indices).
  const average =
    showAverage && riskFreeKnown ? averageLine(visible, riskFreePct) : null;
  const averageEndX = Math.max(
    0,
    ...visible.map((s) => s.volatilityPct as number)
  );

  const toggle = (id: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const changeRiskFree = (value: string) => {
    setRiskFreeInput(value);
    // A cleared box follows the configured rate again on the next visit.
    if (value.trim()) writeStorage(RISK_FREE_KEY, value);
    else removeStorage(RISK_FREE_KEY);
  };

  const submitTicker = (event: FormEvent) => {
    event.preventDefault();
    const ticker = normaliseTicker(tickerInput);
    if (!ticker) {
      setTickerError(t('riskReturn.invalidTicker'));
      return;
    }
    setTickerError(null);
    setBenchmarks((list) => addBenchmark(list, ticker));
    setTickerInput('');
  };

  const returnLabel =
    days > 365 ? t('riskReturn.annualisedReturn') : t('riskReturn.return');
  const volatilityLabel = t('riskReturn.volatility');
  const indexLabel = t('riskReturn.marketIndex');
  const basisLabel = t('riskReturn.priceReturnLocal');
  const availablePresets = PRESET_BENCHMARKS.filter(
    (p) => !benchmarks.some((b) => b.ticker === p.ticker)
  );

  const unavailable = (series: ChartSeries): string | null => {
    if (series.kind === 'benchmark') {
      const ticker = series.id.slice('benchmark:'.length);
      if (benchmarkResults[ticker] === undefined) return t('common.loading');
    }
    return plottable(series) ? null : t('riskReturn.noData');
  };

  return (
    <div className="container mx-auto p-4">
      <h2>{t('riskReturn.title')}</h2>
      <p>{t('riskReturn.description')}</p>

      <div
        style={{
          display: 'flex',
          gap: '1rem',
          flexWrap: 'wrap',
          margin: '1rem 0',
        }}
      >
        <label>
          {t('riskReturn.group')}{' '}
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {(groups.data?.length
              ? groups.data
              : [
                  {
                    slug: DEFAULT_GROUP_SLUG,
                    name: DEFAULT_GROUP_SLUG,
                    members: [],
                  },
                ]
            ).map((g) => (
              <option key={g.slug} value={g.slug}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('riskReturn.window')}{' '}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {WINDOWS.map((w) => (
              <option key={w.key} value={w.days}>
                {t(`riskReturn.windows.${w.key}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={showAverage}
            onChange={(e) => setShowAverage(e.target.checked)}
          />{' '}
          {t('riskReturn.showAverage')}
        </label>
        <label>
          {t('riskReturn.riskFreeRate')}{' '}
          <input
            type="number"
            step="0.25"
            min={-5}
            max={25}
            value={riskFreeText}
            placeholder={points.data ? String(configuredRiskFreePct) : ''}
            onChange={(e) => changeRiskFree(e.target.value)}
            aria-invalid={riskFreeFallback ? true : undefined}
            style={{ width: '5em' }}
          />
          %
          {riskFreeFallback && (
            <em role="status" style={{ marginLeft: '0.5rem' }}>
              {t('riskReturn.riskFreeFallback', { rate: riskFreePct })}
            </em>
          )}
        </label>
      </div>

      {days < RELIABLE_WINDOW_DAYS && (
        <p role="note">{t('riskReturn.shortWindowNote')}</p>
      )}

      {points.error && (
        <p role="alert" style={{ color: 'red' }}>
          {points.error.message}
        </p>
      )}
      {points.loading && <p>{t('common.loading')}</p>}
      {!!points.data?.missing_members.length && (
        <p role="note">
          {t('riskReturn.missingMembers', {
            members: points.data.missing_members
              .map((m) => ownerNames.get(m) ?? m)
              .join(', '),
          })}
        </p>
      )}

      <div
        style={{ width: '100%', height: 460 }}
        data-testid="risk-return-chart"
      >
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 16, right: 24, bottom: 32, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="x"
              name={volatilityLabel}
              unit="%"
              domain={[0, 'auto']}
              label={{ value: volatilityLabel, position: 'bottom' }}
            />
            <YAxis
              type="number"
              dataKey="y"
              name={returnLabel}
              unit="%"
              // Keep 0% and the risk-free rate in view, so the line is seen to
              // start above (or, for a negative rate, below) the origin.
              domain={[(min: number) => Math.min(0, min, riskFreePct), 'auto']}
              label={{ value: returnLabel, angle: -90, position: 'insideLeft' }}
            />
            <ZAxis type="number" dataKey="z" range={[260, 260]} />
            <ReferenceLine y={0} stroke="currentColor" strokeDasharray="4 4" />
            {average && (
              <ReferenceLine
                segment={[
                  { x: 0, y: average.interceptPct },
                  {
                    x: averageEndX,
                    y: average.interceptPct + average.slope * averageEndX,
                  },
                ]}
                stroke="var(--surface-muted-color)"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
              />
            )}
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={
                <PointTooltip
                  returnLabel={returnLabel}
                  volatilityLabel={volatilityLabel}
                  sharpeLabel={t('riskReturn.sharpe')}
                  riskFreePct={riskFreePct}
                  average={average}
                  sideLabels={{
                    above: t('riskReturn.aboveAverage'),
                    below: t('riskReturn.belowAverage'),
                    on: t('riskReturn.onAverage'),
                  }}
                />
              }
            />
            {visible.map((s) => (
              <Scatter
                key={s.id}
                name={s.label}
                data={[
                  {
                    x: s.volatilityPct,
                    y: s.returnPct,
                    label: s.label,
                    ...seriesDetails(s, indexLabel),
                    basis: isIndexSeries(s) ? basisLabel : null,
                    sharpeReturn: s.sharpeReturnPct,
                    z: 1,
                  },
                ]}
                fill={s.color}
                shape={s.kind === 'benchmark' ? 'diamond' : 'circle'}
                isAnimationActive={false}
              />
            ))}
            {average && (
              <Scatter
                name={t('riskReturn.average')}
                data={[
                  {
                    x: average.volatilityPct,
                    y: average.returnPct,
                    label: t('riskReturn.average'),
                    z: 1,
                    isAverage: true,
                  },
                ]}
                fill="var(--surface-muted-color)"
                shape="cross"
                isAnimationActive={false}
              />
            )}
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <section aria-label={t('riskReturn.series')}>
        <h3>{t('riskReturn.portfolioSeries')}</h3>
        <ul
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem 1.25rem',
            listStyle: 'none',
            padding: 0,
          }}
        >
          {portfolioSeries.map((s) => (
            <SeriesToggle
              key={s.id}
              series={s}
              hidden={hidden.has(s.id)}
              onToggle={() => toggle(s.id)}
              unavailableLabel={unavailable(s)}
              removeLabel={t('riskReturn.remove')}
              indexLabel={indexLabel}
              basisLabel={basisLabel}
            />
          ))}
        </ul>

        <h3>{t('riskReturn.benchmarks')}</h3>
        <ul
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem 1.25rem',
            listStyle: 'none',
            padding: 0,
          }}
        >
          {benchmarkSeries.map((s) => (
            <SeriesToggle
              key={s.id}
              series={s}
              hidden={hidden.has(s.id)}
              onToggle={() => toggle(s.id)}
              onRemove={() =>
                setBenchmarks((list) =>
                  removeBenchmark(list, s.id.slice('benchmark:'.length))
                )
              }
              unavailableLabel={unavailable(s)}
              removeLabel={t('riskReturn.remove')}
              indexLabel={indexLabel}
              basisLabel={basisLabel}
            />
          ))}
        </ul>

        <form
          onSubmit={submitTicker}
          style={{
            display: 'flex',
            gap: '0.5rem',
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <label>
            {t('riskReturn.addTicker')}{' '}
            <input
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              placeholder="^FTSE, VWRL.L"
              aria-invalid={tickerError ? true : undefined}
            />
          </label>
          <button type="submit">{t('riskReturn.add')}</button>
          {availablePresets.length > 0 && (
            <select
              aria-label={t('riskReturn.addPreset')}
              value=""
              onChange={(e) =>
                e.target.value &&
                setBenchmarks((list) => addBenchmark(list, e.target.value))
              }
            >
              <option value="">{t('riskReturn.addPreset')}</option>
              {availablePresets.map((p) => (
                <option key={p.ticker} value={p.ticker}>
                  {p.label}
                </option>
              ))}
            </select>
          )}
          {tickerError && (
            <span role="alert" style={{ color: 'red' }}>
              {tickerError}
            </span>
          )}
        </form>
      </section>

      <p style={{ fontSize: '0.85em', opacity: 0.8, marginTop: '1rem' }}>
        {t('riskReturn.methodology')}
      </p>
    </div>
  );
}
