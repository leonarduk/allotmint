export type OwnerSummary = {
  owner: string;
  accounts: string[];
};

export interface Holding {
  ticker: string;
  name: string;
  currency?: string | null;
  units: number;
  acquired_date: string;
  price?: number;
  cost_basis_gbp?: number;
  cost_basis_currency?: string | null;
  effective_cost_basis_gbp?: number;
  effective_cost_basis_currency?: string | null;
  market_value_gbp?: number;
  market_value_currency?: string | null;
  gain_gbp?: number;
  gain_currency?: string | null;
  gain_pct?: number;
  current_price_gbp?: number | null;
  current_price_currency?: string | null;
  /** Date of the last known price for this holding */
  last_price_date?: string | null;
  /** Timestamp of the last known price for this holding */
  last_price_time?: string | null;
  /** Whether the current price may be stale */
  is_stale?: boolean;
  latest_source?: string | null;
  day_change_gbp?: number;
  day_change_currency?: string | null;
  instrument_type?: string | null;
  sector?: string | null;
  region?: string | null;

  days_held?: number;
  sell_eligible?: boolean;
  days_until_eligible?: number | null;
  next_eligible_sell_date?: string | null;
}

export type Account = {
  account_type: string;
  currency: string;
  last_updated?: string;
  value_estimate_gbp: number;
  value_estimate_currency?: string | null;
  holdings: Holding[];
  owner?: string;
};

export type Portfolio = {
  owner: string;
  as_of: string;
  trades_this_month: number;
  trades_remaining: number;
  total_value_estimate_gbp: number;
  total_value_estimate_currency?: string | null;
  accounts: Account[];
};

export type GroupSummary = {
  slug: string;
  name: string;
  members: string[];
};

export type GroupPortfolio = {
  group: string;
  name: string;
  as_of: string;
  members: string[];
  total_value_estimate_gbp: number;
  total_value_estimate_currency?: string | null;
  trades_this_month?: number;
  trades_remaining?: number;
  accounts: Account[];
  members_summary: {
    owner: string;
    total_value_estimate_gbp: number;
    total_value_estimate_currency?: string | null;
    trades_this_month: number;
    trades_remaining: number;
  }[];
  subtotals_by_account_type: Record<string, number>;
};

export type InstrumentSummary = {
  ticker: string;
  name: string;
  grouping?: string | null;
  exchange?: string | null;
  currency?: string | null;
  units: number;
  market_value_gbp: number;
  market_value_currency?: string | null;
  gain_gbp: number;
  gain_currency?: string | null;
  instrument_type?: string | null;
  gain_pct?: number;

  /* last-price enrichment */
  last_price_gbp?: number | null;
  last_price_currency?: string | null;
  last_price_date?: string | null;
  change_7d_pct?: number | null;
  change_30d_pct?: number | null;
};

export type SectorContribution = {
  sector: string;
  market_value_gbp: number;
  gain_gbp: number;
  cost_gbp: number;
  currency?: string | null;
  gain_pct?: number | null;
  contribution_pct?: number | null;
};

export type RegionContribution = {
  region: string;
  market_value_gbp: number;
  gain_gbp: number;
  cost_gbp: number;
  currency?: string | null;
  gain_pct?: number | null;
  contribution_pct?: number | null;
};

export interface PerformancePoint {
  date: string;
  value: number;
  daily_return?: number | null;
  weekly_return?: number | null;
  cumulative_return?: number | null;
  running_max?: number;
  drawdown?: number | null;
}

export interface PerformanceResponse {
  history: PerformancePoint[];
  time_weighted_return?: number | null;
  xirr?: number | null;
}

export interface HoldingValue {
  ticker: string;
  exchange: string;
  units: number;
  price?: number | null;
  value?: number | null;
}

export interface ValueAtRiskPoint {
  date: string;
  var: number;
}

export interface VarBreakdown {
  ticker: string;
  contribution: number;
  var?: {
    [horizon: string]: number | null;
  };
  sharpe_ratio?: number | null;
}

export interface ValueAtRiskResponse {
  owner: string;
  as_of: string;
  var: {
    [horizon: string]: number | null;
  };
  sharpe_ratio?: number | null;
}

export interface AlphaResponse {
  alpha_vs_benchmark: number | null;
  benchmark: string;
}

export interface TrackingErrorResponse {
  tracking_error: number | null;
  benchmark: string;
}

export interface MaxDrawdownResponse {
  max_drawdown: number | null;
}

export interface ReturnComparisonResponse {
  owner: string;
  cagr: number | null;
  cash_apy: number | null;
}

export interface InstrumentDetailMini {
  [range: string]: {
    date: string;
    close: number;
    close_gbp: number;
  }[];
}

export interface NewsItem {
  headline: string;
  url: string;
  source?: string | null;
  published_at?: string | null;
}

export interface SectorPerformance {
  sector: string;
  change: number;
}

export interface IndexPerformance {
  value: number;
  change?: number | null;
}

export interface MarketOverview {
  indexes: Record<string, IndexPerformance>;
  sectors: SectorPerformance[];
  headlines: NewsItem[];
}

export interface InstrumentPosition {
  owner: string;
  account: string;
  units: number | null;
  market_value_gbp?: number | null;
  unrealised_gain_gbp?: number | null;
  gain_pct?: number | null;
}

export interface InstrumentDetail {
  ticker?: string | null;
  prices: unknown;
  positions: InstrumentPosition[];
  mini?: InstrumentDetailMini;
  name?: string | null;
  sector?: string | null;
  currency?: string | null;
  instrument_type?: string | null;
  rows?: number | null;
  from?: string | null;
  to?: string | null;
  base_currency?: string | null;
}

export interface Transaction {
  owner: string;
  account: string;
  date?: string;
  kind?: string;
  type?: string | null;
  amount_minor?: number | null;
  currency?: string | null;
  security_ref?: string | null;
  ticker?: string | null;
  shares?: number | null;
  units?: number | null;
  price_gbp?: number | null;
  fees?: number | null;
  comments?: string | null;
  reason?: string | null;
}

export interface TransactionWithCompliance extends Transaction {
  warnings: string[];
}

export interface PriceEntry {
  Date: string;
  Open?: number | null;
  High?: number | null;
  Low?: number | null;
  Close?: number | null;
  Volume?: number | null;
  Ticker?: string;
  Source?: string;
}

export interface UserConfig {
  hold_days_min?: number;
  max_trades_per_month?: number;
  approval_exempt_types?: string[];
  approval_exempt_tickers?: string[];
}

export interface Approval {
  ticker: string;
  approved_on: string;
}

export interface ApprovalsResponse {
  approvals: Approval[];
}

export interface TimeseriesSummary {
  ticker: string;
  exchange: string;
  name?: string | null;
  earliest: string;
  latest: string;
  completeness: number;
  latest_source?: string | null;
  main_source?: string | null;
}

export interface InstrumentMetadata {
  ticker: string;
  exchange?: string | null;
  name: string;
  region?: string | null;
  sector?: string | null;
  grouping?: string | null;
  currency?: string | null;
  instrument_type?: string | null;
  instrumentType?: string | null;
}

export interface QuoteRow {
  name: string | null;
  symbol: string;
  last: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  change: number | null;
  changePct: number | null;
  volume: number | null;
  marketTime: string | null;
  marketState: string;
}

export interface MoverRow {
  ticker: string;
  name: string;
  change_pct: number;
  last_price_gbp?: number | null;
  last_price_date?: string | null;
  market_value_gbp?: number | null;
}

export type Alert = {
  ticker: string;
  change_pct: number;
  message: string;
  timestamp: string;
};

export type Nudge = {
  id: string;
  message: string;
  timestamp: string;
};

export interface ScenarioEvent {
  id: string;
  name: string;
}

export interface ScenarioHorizonResult {
  baseline_total_value_gbp: number | null;
  shocked_total_value_gbp: number | null;
}

export interface ScenarioResult {
  owner: string;
  horizons: Record<string, ScenarioHorizonResult>;
}

export type ComplianceResult = {
  owner: string;
  warnings: string[];
  trade_counts: Record<string, number>;
  hold_countdowns?: Record<string, number>;
  trades_this_month?: number;
  trades_remaining?: number;
};

export interface ScreenerResult {
  rank: number;
  ticker: string;
  name?: string | null;
  peg_ratio: number | null;
  pe_ratio: number | null;
  de_ratio: number | null;
  lt_de_ratio: number | null;
  interest_coverage: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
  fcf: number | null;
  eps: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  ebitda_margin: number | null;
  roa: number | null;
  roe: number | null;
  roi: number | null;
  dividend_yield: number | null;
  dividend_payout_ratio: number | null;
  beta: number | null;
  shares_outstanding: number | null;
  float_shares: number | null;
  market_cap: number | null;
  high_52w: number | null;
  low_52w: number | null;
  avg_volume: number | null;
}

export interface SyntheticHolding {
  ticker: string;
  units: number;
  price?: number;
  purchase_date?: string;
}

export interface VirtualPortfolio {
  id?: number;
  name: string;
  accounts: string[];
  holdings: SyntheticHolding[];
}

export interface TradingSignal {
  ticker: string;
  name?: string;
  action: 'buy' | 'sell' | 'BUY' | 'SELL';
  reason: string;
  confidence?: number;
  rationale?: string;
  currency?: string | null;
  instrument_type?: string | null;
}

export interface OpportunityEntry extends MoverRow {
  side: 'gainers' | 'losers';
  signal?: TradingSignal | null;
}

export interface CustomQuery {
  start?: string;
  end?: string;
  owners?: string[];
  tickers?: string[];
  metrics?: string[];
}

export interface SavedQuery {
  id: string;
  name: string;
  params: CustomQuery;
}

export interface TradeSuggestion {
  ticker: string;
  action: string;
  amount: number;
}

export interface Quest {
  id: string;
  title: string;
  xp: number;
  completed: boolean;
}

export interface QuestResponse {
  quests: Quest[];
  xp: number;
  streak: number;
}

export interface TrailTask {
  id: string;
  title: string;
  type: "daily" | "once";
  commentary: string;
  completed: boolean;
}

export interface TrailCompletionTotals {
  completed: number;
  total: number;
}

export interface TrailResponse {
  tasks: TrailTask[];
  xp: number;
  streak: number;
  daily_totals: Record<string, TrailCompletionTotals>;
  today: string;
}
