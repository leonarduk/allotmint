// Merge, derive and filter the Screener's risk/return columns
// (allotmint#10607). The figures come from GET /screener/risk-return; the
// fundamentals rows come from GET /screener. Both are keyed by ticker.
import type {
  RiskReturnBasis,
  RiskReturnRow,
  RiskReturnStats,
  ScreenerResult,
  ScreenerRiskReturn,
} from '../types';

export const RISK_PERIODS = ['3', '5', '10'] as const;
export type RiskPeriod = (typeof RISK_PERIODS)[number];
export type RiskCurrency = 'gbp' | 'local';
/** Which Sharpe a min-Sharpe filter applies to: one period, or all three. */
export type SharpeScope = RiskPeriod | 'all';

/**
 * Why a ticker's risk cells are blank: "missing" = no stored prices,
 * "short" = history doesn't cover the window, "absent" = not in the payload.
 */
export type RiskStatus = 'ok' | 'missing' | 'short' | 'absent';

export interface RiskColumns {
  sharpe_3y: number | null;
  sharpe_5y: number | null;
  sharpe_10y: number | null;
  /** Lowest of the three Sharpes; null unless all three exist. */
  min_sharpe: number | null;
  /** The figures below are for the selected period. */
  risk_return: number | null;
  risk_volatility: number | null;
  risk_max_drawdown: number | null;
  risk_currency: string | null;
  risk_basis: RiskReturnBasis | null;
  risk_status: RiskStatus;
}

export type ScreenerRow = ScreenerResult & Partial<RiskColumns>;

export interface RiskFilters {
  /** Minimum Sharpe, as typed (blank = off). */
  minSharpe: string;
  sharpeScope: SharpeScope;
  /** Largest acceptable worst fall as a positive fraction (0.3 = 30%), as typed. */
  maxDrawdown: string;
}

export const DEFAULT_RISK_FILTERS: RiskFilters = {
  minSharpe: '',
  sharpeScope: 'all',
  maxDrawdown: '',
};

function stats(
  row: RiskReturnRow,
  period: RiskPeriod,
  currency: RiskCurrency
): RiskReturnStats | null {
  return row.windows?.[period]?.[currency] ?? null;
}

function sharpe(
  row: RiskReturnRow,
  period: RiskPeriod,
  currency: RiskCurrency
) {
  return stats(row, period, currency)?.sharpe ?? null;
}

function minOf(values: (number | null)[]): number | null {
  if (values.some((v) => v == null)) return null;
  return Math.min(...(values as number[]));
}

/** Risk columns for one ticker; `row` undefined means the payload omitted it. */
export function riskColumnsFor(
  row: RiskReturnRow | undefined,
  missing: boolean,
  currency: RiskCurrency,
  period: RiskPeriod
): RiskColumns {
  const sharpes = RISK_PERIODS.map((p) =>
    row ? sharpe(row, p, currency) : null
  );
  const selected = row ? stats(row, period, currency) : null;
  let status: RiskStatus = 'ok';
  if (!row) status = missing ? 'missing' : 'absent';
  else if (!selected) status = 'short';
  return {
    sharpe_3y: sharpes[0],
    sharpe_5y: sharpes[1],
    sharpe_10y: sharpes[2],
    min_sharpe: minOf(sharpes),
    risk_return: selected?.return ?? null,
    risk_volatility: selected?.volatility ?? null,
    risk_max_drawdown: selected?.max_drawdown ?? null,
    risk_currency: row ? (currency === 'gbp' ? 'GBP' : row.currency) : null,
    risk_basis: row?.return_basis ?? null,
    risk_status: status,
  };
}

/** Attach risk columns to each fundamentals row by (case-insensitive) ticker. */
export function mergeRiskReturn(
  rows: ScreenerResult[],
  data: ScreenerRiskReturn | null,
  currency: RiskCurrency,
  period: RiskPeriod
): ScreenerRow[] {
  if (!data) return rows;
  // The engine normalises a bare US symbol ("SPY") to "SPY.N", so index each
  // row under both forms; the S&P 500 watchlist sends bare symbols.
  const byTicker = new Map<string, RiskReturnRow>();
  for (const r of data.rows) {
    byTicker.set(r.ticker.toUpperCase(), r);
    if (r.requested) byTicker.set(r.requested.toUpperCase(), r);
  }
  const missing = new Set(
    data.missing.flatMap((t) => {
      const upper = t.toUpperCase();
      return upper.endsWith('.N') ? [upper, upper.slice(0, -2)] : [upper];
    })
  );
  return rows.map((r) => {
    const key = r.ticker.toUpperCase();
    return {
      ...r,
      ...riskColumnsFor(byTicker.get(key), missing.has(key), currency, period),
    };
  });
}

function parseThreshold(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function scopedSharpe(row: ScreenerRow, scope: SharpeScope): number | null {
  if (scope === 'all') return row.min_sharpe ?? null;
  return row[`sharpe_${scope}y` as const] ?? null;
}

/**
 * Whether a merged row passes the risk filters. A row without the figure a
 * filter needs fails it: an unknown Sharpe is not evidence of a good one.
 */
export function passesRiskFilters(
  row: ScreenerRow,
  filters: RiskFilters
): boolean {
  const minSharpe = parseThreshold(filters.minSharpe);
  if (minSharpe != null) {
    const value = scopedSharpe(row, filters.sharpeScope);
    if (value == null || value < minSharpe) return false;
  }
  const maxDrawdown = parseThreshold(filters.maxDrawdown);
  if (maxDrawdown != null) {
    const fall = row.risk_max_drawdown;
    if (fall == null || Math.abs(fall) > Math.abs(maxDrawdown)) return false;
  }
  return true;
}

/** True when any risk filter is set, so the page can explain an emptied table. */
export function hasRiskFilters(filters: RiskFilters): boolean {
  return (
    parseThreshold(filters.minSharpe) != null ||
    parseThreshold(filters.maxDrawdown) != null
  );
}
