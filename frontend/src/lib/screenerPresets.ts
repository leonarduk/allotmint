import type { SavedScreen } from './savedScreensStore';

/**
 * Built-in starting-point screens, shown as buttons above the screener
 * form. Read-only: "Save as…" copies one into the user's list to tweak.
 *
 * Thresholds avoid D/E: data vendors disagree on whether it is a ratio or a
 * percentage, so a fixed number would silently filter everything out for one
 * of the two scales. Fraction fields (growth, margins, returns, payout,
 * dividend yield -- the engine normalises every provider's yield to a
 * fraction) use 0.10 = 10%. FCF is in reporting currency, so "1" just means
 * "positive".
 */
export interface ScreenPreset extends SavedScreen {
  id: string;
  description: string;
}

export const SCREEN_PRESETS: readonly ScreenPreset[] = [
  {
    id: 'quality',
    name: 'Quality compounders',
    description:
      'High returns on equity and fat margins, funded without much debt.',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      roe_min: '0.15',
      operating_margin_min: '0.15',
      revenue_growth_min: '0.05',
      net_debt_to_ebitda_max: '2',
      interest_coverage_min: '8',
    },
  },
  {
    id: 'deep-value',
    name: 'Deep value',
    description:
      'Cheap on earnings, book and EV/EBITDA, with an Altman Z floor to screen out value traps.',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      pe_max: '12',
      pb_max: '1.5',
      ev_ebitda_max: '8',
      current_ratio_min: '1',
      altman_z_min: '1.8',
    },
  },
  {
    id: 'garp',
    name: 'Growth at a reasonable price',
    description:
      'Earnings and revenue growing at a sensible multiple of that growth (PEG ≤ 1.5).',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      peg_max: '1.5',
      pe_max: '25',
      earnings_growth_min: '0.1',
      revenue_growth_min: '0.05',
      roe_min: '0.12',
    },
  },
  {
    id: 'income',
    name: 'Sustainable income',
    description:
      'Yield of at least 3%, covered by earnings and cash flow, with serviceable debt. Sort by Div% to rank by yield.',
    watchlist: 'FTSE 100',
    tickers: '',
    filters: {
      dividend_yield_min: '0.03',
      dividend_payout_ratio_max: '0.75',
      fcf_min: '1',
      interest_coverage_min: '4',
      net_debt_to_ebitda_max: '3',
    },
  },
  {
    id: 'defensive',
    name: 'Low volatility defensives',
    description:
      'Low beta, consistently profitable, comfortably solvent businesses.',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      beta_max: '0.8',
      net_margin_min: '0.05',
      altman_z_min: '3',
      current_ratio_min: '1.2',
    },
  },
  {
    id: 'fortress',
    name: 'Fortress balance sheet',
    description:
      'Little or no net debt, strong liquidity and very high interest cover.',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      net_debt_to_ebitda_max: '1',
      interest_coverage_min: '10',
      current_ratio_min: '1.5',
      quick_ratio_min: '1',
      altman_z_min: '3',
    },
  },
  {
    id: 'cash-generators',
    name: 'Cash generators',
    description:
      'High EBITDA margins and returns on assets, positive free cash flow, not expensive.',
    watchlist: 'FTSE 350',
    tickers: '',
    filters: {
      fcf_min: '1',
      ebitda_margin_min: '0.2',
      roa_min: '0.08',
      ev_ebitda_max: '12',
    },
  },
  {
    id: 'us-growth',
    name: 'US high growth',
    description: 'Fast-growing S&P 500 companies with high gross margins.',
    watchlist: 'S&P 500',
    tickers: '',
    filters: {
      revenue_growth_min: '0.15',
      earnings_growth_min: '0.15',
      gross_margin_min: '0.4',
      operating_margin_min: '0.1',
    },
  },
];

function nonEmpty(filters: Record<string, string | undefined>) {
  return Object.entries(filters).filter(([, v]) => v?.trim());
}

/**
 * The preset the form currently matches exactly, if any. Derived rather than
 * stored, so editing any field after picking a preset deselects it.
 */
export function presetMatching(
  watchlist: string,
  filters: Record<string, string | undefined>
): ScreenPreset | undefined {
  const current = nonEmpty(filters);
  return SCREEN_PRESETS.find(
    (p) =>
      p.watchlist === watchlist &&
      current.length === Object.keys(p.filters).length &&
      current.every(([k, v]) => Number(v) === Number(p.filters[k]))
  );
}
