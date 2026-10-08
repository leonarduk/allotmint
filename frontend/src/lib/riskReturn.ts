// Series building for the "Returns vs Volatility" page: the group, each owner,
// each owner's account and any benchmark indices, as one point per series.
import type {
  BenchmarkRiskReturn,
  GroupRiskReturn,
  RiskReturnPoint,
} from '../types';

export interface Benchmark {
  ticker: string;
  label: string;
}

/** Shown on first visit; the user can remove these or add others. */
export const DEFAULT_BENCHMARKS: Benchmark[] = [
  { ticker: '^FTSE', label: 'FTSE 100' },
  { ticker: '^IXIC', label: 'NASDAQ' },
  { ticker: '^GSPC', label: 'S&P 500' },
];

/** One-click additions offered alongside the free-text ticker box. */
export const PRESET_BENCHMARKS: Benchmark[] = [
  ...DEFAULT_BENCHMARKS,
  { ticker: '^FTMC', label: 'FTSE 250' },
  { ticker: '^DJI', label: 'Dow Jones' },
  { ticker: '^STOXX50E', label: 'Euro Stoxx 50' },
  { ticker: '^N225', label: 'Nikkei 225' },
];

export type SeriesKind = RiskReturnPoint['kind'] | 'benchmark';

export interface ChartSeries {
  id: string;
  label: string;
  kind: SeriesKind;
  color: string;
  /** Return in percent: annualised for windows over a year, else the period total. */
  returnPct: number | null;
  volatilityPct: number | null;
}

// Categorical palette: distinct hues readable on light and dark backgrounds.
const PALETTE = [
  '#2563eb',
  '#16a34a',
  '#dc2626',
  '#9333ea',
  '#ea580c',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#7c3aed',
  '#ca8a04',
];
const GROUP_COLOR = '#111827';

export function seriesColor(index: number): string {
  return PALETTE[index % PALETTE.length];
}

function pct(value: number | null | undefined): number | null {
  return value == null || !Number.isFinite(value) ? null : value * 100;
}

function returnPct(
  point: { period_return: number | null; annualised_return: number | null },
  days: number
): number | null {
  return pct(days > 365 ? point.annualised_return : point.period_return);
}

function accountLabel(account: string): string {
  return account.length <= 4 ? account.toUpperCase() : account;
}

export function portfolioSeriesId(point: RiskReturnPoint): string {
  if (point.kind === 'group') return 'group';
  if (point.kind === 'owner') return `owner:${point.owner}`;
  return `account:${point.owner}:${point.account}`;
}

export function benchmarkSeriesId(ticker: string): string {
  return `benchmark:${ticker}`;
}

interface BuildOptions {
  days: number;
  ownerNames: Map<string, string>;
  groupLabel: string;
  ownerTotalLabel: (owner: string) => string;
}

export function buildPortfolioSeries(
  data: GroupRiskReturn | null | undefined,
  { days, ownerNames, groupLabel, ownerTotalLabel }: BuildOptions
): ChartSeries[] {
  if (!data) return [];
  return data.points.map((point, index) => {
    const owner = point.owner
      ? (ownerNames.get(point.owner) ?? point.owner)
      : '';
    const label =
      point.kind === 'group'
        ? groupLabel
        : point.kind === 'owner'
          ? ownerTotalLabel(owner)
          : `${owner} ${accountLabel(point.account ?? '')}`;
    return {
      id: portfolioSeriesId(point),
      label,
      kind: point.kind,
      color: point.kind === 'group' ? GROUP_COLOR : seriesColor(index),
      returnPct: returnPct(point, days),
      volatilityPct: pct(point.volatility),
    };
  });
}

export function buildBenchmarkSeries(
  benchmarks: Benchmark[],
  results: Record<string, BenchmarkRiskReturn | null | undefined>,
  days: number,
  colorOffset: number
): ChartSeries[] {
  return benchmarks.map((benchmark, index) => {
    const result = results[benchmark.ticker];
    return {
      id: benchmarkSeriesId(benchmark.ticker),
      label: benchmark.label,
      kind: 'benchmark',
      color: seriesColor(colorOffset + index),
      returnPct: result ? returnPct(result, days) : null,
      volatilityPct: result ? pct(result.volatility) : null,
    };
  });
}

/** Series that can be drawn: both coordinates known. */
export function plottable(series: ChartSeries): boolean {
  return series.returnPct != null && series.volatilityPct != null;
}

/** Normalise a typed ticker; null when it can't be a ticker. */
export function normaliseTicker(raw: string): string | null {
  const ticker = raw.trim().toUpperCase();
  return /^\^?[A-Z0-9][A-Z0-9._-]{0,31}$/.test(ticker) && !ticker.includes('..')
    ? ticker
    : null;
}

/** Add ``ticker`` (labelled from the presets when known) unless already present. */
export function addBenchmark(list: Benchmark[], ticker: string): Benchmark[] {
  if (list.some((b) => b.ticker === ticker)) return list;
  const preset = PRESET_BENCHMARKS.find((b) => b.ticker === ticker);
  return [...list, preset ?? { ticker, label: ticker }];
}

export function removeBenchmark(
  list: Benchmark[],
  ticker: string
): Benchmark[] {
  return list.filter((b) => b.ticker !== ticker);
}

/** Parse a stored benchmark list, falling back to the defaults. */
export function parseStoredBenchmarks(raw: string | null): Benchmark[] {
  if (!raw) return DEFAULT_BENCHMARKS;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_BENCHMARKS;
    return parsed.filter(
      (b): b is Benchmark =>
        typeof b?.ticker === 'string' &&
        typeof b?.label === 'string' &&
        normaliseTicker(b.ticker) === b.ticker
    );
  } catch {
    return DEFAULT_BENCHMARKS;
  }
}
