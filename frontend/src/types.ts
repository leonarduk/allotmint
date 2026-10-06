export type OwnerSummary = {
  owner: string;
  accounts: string[];
  full_name?: string | null;
  email?: string | null;
  has_transactions_artifact?: boolean;
};

export interface Holding {
  ticker: string;
  name: string;
  currency?: string | null;
  units: number;
  acquired_date?: string | null;
  price?: number | null;
  cost_basis_gbp?: number | null;
  cost_basis_currency?: string | null;
  effective_cost_basis_gbp?: number | null;
  effective_cost_basis_currency?: string | null;
  /**
   * How cost_basis/effective_cost_basis_gbp were derived: "book" (a real
   * booked cost), "derived" (a real historical price near a known
   * acquisition date), "unknown" (no booked cost and no acquisition date --
   * cost was set equal to current market value as a last resort and the
   * resulting gain/gain_pct is not a fact, see #7220), "cash", or "none".
   */
  cost_basis_source?: string | null;
  market_value_gbp?: number | null;
  market_value_currency?: string | null;
  gain_gbp?: number | null;
  gain_currency?: string | null;
  gain_pct?: number | null;
  /** Dividends and interest received on this position, GBP (#9038). */
  income_gbp?: number | null;
  /** Gain already realised on units of this position that were sold, GBP. */
  realised_gain_gbp?: number | null;
  /** gain_gbp + realised_gain_gbp + income_gbp; null when any part is unknown. */
  total_return_gbp?: number | null;
  /** total_return_gbp over all cost put into the position, as a percentage. */
  total_return_pct?: number | null;
  current_price_gbp?: number | null;
  current_price_currency?: string | null;
  /** Date of the last known price for this holding */
  last_price_date?: string | null;
  /** Timestamp of the last known price for this holding */
  last_price_time?: string | null;
  /** Whether the current price may be stale */
  is_stale?: boolean | null;
  latest_source?: string | null;
  day_change_gbp?: number | null;
  day_change_currency?: string | null;
  instrument_type?: string | null;
  sector?: string | null;
  region?: string | null;
  forward_7d_change_pct?: number | null;
  forward_30d_change_pct?: number | null;

  days_held?: number | null;
  sell_eligible?: boolean | null;
  days_until_eligible?: number | null;
  next_eligible_sell_date?: string | null;
}

export type Account = {
  account_type: string;
  currency: string;
  last_updated?: string | null;
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
  slug: string;
  name: string;
  as_of: string;
  members: string[];
  total_value_estimate_gbp: number;
  total_value_estimate_currency?: string | null;
  trades_this_month?: number;
  trades_remaining?: number;
  accounts: Account[];
  members_summary?: {
    owner: string;
    total_value_estimate_gbp: number;
    total_value_estimate_currency?: string | null;
    trades_this_month: number;
    trades_remaining: number;
  }[];
  subtotals_by_account_type?: Record<string, number>;
};

export type InstrumentSummary = {
  ticker: string;
  name: string;
  grouping?: string | null;
  sector?: string | null;
  exchange?: string | null;
  currency?: string | null;
  units: number;
  market_value_gbp: number;
  market_value_currency?: string | null;
  gain_gbp: number;
  gain_currency?: string | null;
  instrument_type?: string | null;
  gain_pct?: number;
  /** "unknown" when any holding's cost is a guess, so its gain is not a fact (#7785). */
  cost_basis_source?: string | null;

  /* last-price enrichment */
  last_price_gbp?: number | null;
  last_price_currency?: string | null;
  last_price_date?: string | null;
  change_7d_pct?: number | null;
  change_30d_pct?: number | null;
};

export interface InstrumentGroupDefinition {
  id: string;
  name: string;
  aliases?: string[] | null;
  category?: string | null;
  category_name?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

export type SectorContribution = {
  sector: string;
  market_value_gbp: number;
  gain_gbp: number;
  cost_gbp: number;
  currency?: string | null;
  gain_pct?: number | null;
  contribution_pct?: number | null;
  /** Market value of holdings left out of gain/cost (unreliable cost basis, #8488). */
  unknown_cost_market_value_gbp?: number;
};

export type RegionContribution = {
  region: string;
  market_value_gbp: number;
  gain_gbp: number;
  cost_gbp: number;
  currency?: string | null;
  gain_pct?: number | null;
  contribution_pct?: number | null;
  /** Market value of holdings left out of gain/cost (unreliable cost basis, #8488). */
  unknown_cost_market_value_gbp?: number;
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

export interface DataQualityIssue {
  date: string;
  value: number;
  previousValue: number;
  nextValue: number;
}

export interface PerformanceResponse {
  history: PerformancePoint[];
  time_weighted_return?: number | null;
  xirr?: number | null;
  reportingDate?: string | null;
  previousDate?: string | null;
  dataQualityIssues?: DataQualityIssue[];
  /**
   * Group scope only (#7228): true when at least one member's transaction
   * ledger was missing, so time_weighted_return/xirr are computed from an
   * incomplete cash-flow picture (their holdings still count toward the
   * combined value series) and should be presented as unreliable rather
   * than an exact figure.
   */
  partial?: boolean;
  missingMembers?: string[];
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
  name?: string;
  contribution: number;
  scenario_amount_gbp?: number | null;
  relative_change_percent?: number | null;
  relative_drop_percent?: number | null;
  var?: {
    [horizon: string]: number | null;
  };
  sharpe_ratio?: number | null;
}

export interface VarScenario {
  date: string;
  portfolio_return: number;
  loss_percent: number;
}

export interface VarBreakdownResponse {
  breakdown: VarBreakdown[];
  scenarios: VarScenario[];
  varDate: string | null;
  varLossPercent: number | null;
}

export interface ValueAtRiskResponse {
  owner: string;
  as_of: string;
  var: {
    [horizon: string]: number | null;
  };
  sharpe_ratio?: number | null;
}

export interface DataQualityGapPeriod {
  start: string;
  end: string;
  missing_business_days: number;
}

export interface DataQualityOutlier {
  date: string;
  value: number;
  z_score: number;
}

export interface TimeseriesQualityPosition {
  ticker: string;
  exchange: string;
  total_points: number;
  first_date: string | null;
  last_date: string | null;
  gap_count: number;
  gaps: DataQualityGapPeriod[];
  duplicate_dates: string[];
  outliers: DataQualityOutlier[];
}

export interface DataQualityTimeseriesResponse {
  count: number;
  positions: TimeseriesQualityPosition[];
}

export interface AlphaSeriesPoint {
  date: string;
  portfolio_cumulative_return: number;
  benchmark_cumulative_return: number;
  excess_cumulative_return: number;
}

export interface AlphaResponse {
  alpha_vs_benchmark: number | null;
  benchmark: string;
  portfolio_cumulative_return?: number | null;
  benchmark_cumulative_return?: number | null;
  series?: AlphaSeriesPoint[];
}

export interface TrackingErrorPoint {
  date: string;
  portfolio_return: number;
  benchmark_return: number;
  active_return: number;
}

export interface TrackingErrorResponse {
  tracking_error: number | null;
  benchmark: string;
  active_returns?: TrackingErrorPoint[];
  daily_active_standard_deviation?: number | null;
}

export interface DrawdownSeriesPoint {
  date: string;
  portfolio_value: number;
  running_max: number;
  drawdown: number;
}

export interface DrawdownExtrema {
  date: string;
  value: number;
  drawdown?: number;
}

export interface MaxDrawdownResponse {
  max_drawdown: number | null;
  series?: DrawdownSeriesPoint[];
  peak?: DrawdownExtrema | null;
  trough?: DrawdownExtrema | null;
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
  stale?: boolean;
}

export type SectorRegion = 'global' | 'us' | 'uk';

/** Change window for Market Overview: 1M = 30 days, 3M = 90 days. */
export type MarketPeriod = '1D' | '1W' | '1M' | '3M' | '1Y';

/** One sector row of `GET /market/sectors` and `/market/overview` (#9381). */
export interface RegionSectorPerformance {
  sector: string;
  change: number;
  /** `etf`: proxy ETF day change; `basket`: equal-weighted constituents. */
  source: 'etf' | 'basket';
}

export interface RegionSectors {
  region: SectorRegion;
  period?: MarketPeriod;
  sectors: RegionSectorPerformance[];
}

export interface SectorConstituent {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
}

/** `GET /market/sectors/{region}/{sector}` (#9381). */
export interface SectorDetail {
  region: SectorRegion;
  sector: string;
  basis: 'etf' | 'basket';
  proxy: { ticker: string; name: string } | null;
  returns: Record<'1D' | '1W' | '1M' | 'YTD', number | null>;
  history: { date: string; value: number }[];
  constituents: SectorConstituent[];
}

export interface IndexPerformance {
  value: number;
  change: number;
}

/** `GET /market/indexes`: index level and % change over `period`. */
export interface MarketIndexes {
  period: MarketPeriod;
  indexes: Record<string, IndexPerformance>;
}

export interface MarketOverview {
  indexes: Record<string, IndexPerformance>;
  sectors: RegionSectorPerformance[];
  headlines: NewsItem[];
}

/**
 * One holding of an instrument, projected by the backend from the same
 * enriched holding row the dashboard uses (#8533). Monetary fields are GBP.
 */
export interface InstrumentPosition {
  owner: string;
  account: string;
  units: number | null;
  market_value_gbp?: number | null;
  /** Legacy alias of `gain_gbp`. */
  unrealised_gain_gbp?: number | null;
  gain_gbp?: number | null;
  gain_pct?: number | null;
  /** Null when the cost basis is unknown or unreliable. */
  cost_basis_gbp?: number | null;
  avg_cost_gbp?: number | null;
  current_price_gbp?: number | null;
  /** Share of the owner's total portfolio value. */
  weight_pct?: number | null;
  acquired_date?: string | null;
  days_held?: number | null;
  cost_basis_source?: string | null;
  cost_basis_warning?: string | null;
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
  id?: string | null;
  external_id?: string | null;
  date?: string | null;
  kind?: string | null;
  type?: string | null;
  amount_minor?: number | null;
  currency?: string | null;
  security_ref?: string | null;
  ticker?: string | null;
  instrument_name?: string | null;
  shares?: number | null;
  units?: number | null;
  price_gbp?: number | null;
  fees?: number | null;
  comments?: string | null;
  reason?: string | null;
  reason_to_buy?: string | null;
  /**
   * Balancing entry injected by holdings reconciliation rather than a trade the
   * owner actually placed.  Carried by the API contract but previously absent
   * from this interface.
   */
  synthetic?: boolean;
  /**
   * Derived by the backend for SELL rows using Section 104 average cost.
   * `realised_gain_gbp` is null when some units sold have no known cost
   * (`unmatched_units` > 0), e.g. positions held before records begin.
   */
  realised_gain_gbp?: number | null;
  cost_basis_gbp?: number | null;
  proceeds_gbp?: number | null;
  unmatched_units?: number | null;
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

export interface DataExplorerEntry {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number | null;
  modified: string;
}

export interface DataExplorerDirectory {
  path: string;
  entries: DataExplorerEntry[];
}

export interface DataExplorerFile {
  path: string;
  size: number;
  modified: string;
  truncated: boolean;
  content: string;
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
  isin?: string | null;
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
  /** ISO currency code from the quote provider, when available (#7218). */
  currency?: string | null;
  /** Provider instrument classification, e.g. "INDEX", "EQUITY", "ETF". */
  quoteType?: string | null;
}

export interface MoverRow {
  ticker: string;
  name: string;
  change_pct: number;
  last_price_gbp?: number | null;
  last_price_date?: string | null;
  market_value_gbp?: number | null;
  instrument_type?: string | null;
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
  /** Share of invested value with real price history for the event (0-100). */
  coverage_pct?: number | null;
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
  pb_ratio?: number | null;
  ps_ratio?: number | null;
  ev_ebitda?: number | null;
  book_value?: number | null;
  book_value_as_of?: string | null;
  forward_pe?: number | null;
  total_debt?: number | null;
  total_cash?: number | null;
  net_debt?: number | null;
  price?: number | null;
  currency?: string | null;
  financial_currency?: string | null;
  revenue?: number | null;
  revenue_growth?: number | null;
  earnings_growth?: number | null;
  instrument_type?: string | null;
}

/** NAV freshness from the valuation profile (allotmint#9197). */
export type NavStatus = 'current' | 'stale' | 'undated';

/**
 * Valuation profile from GET /screener/valuation (allotmint-pro#259).
 * Ratios are fractions (0.05 = 5%); a value no source supplies is null.
 */
export interface InstrumentValuation {
  ticker: string;
  name: string | null;
  instrument_type: string | null;
  is_closed_end_fund: boolean;
  price: number | null;
  price_currency: string | null;
  valuation: {
    pe_ratio: number | null;
    forward_pe: number | null;
    pb_ratio: number | null;
    ev_ebitda: number | null;
  };
  nav: {
    nav_per_share: number | null;
    currency: string | null;
    as_of: string | null;
    /** "metadata" | "reported_book_value" | null */
    source: string | null;
    /** price / NAV - 1: negative is a discount. */
    premium_discount: number | null;
    /** Days since as_of; null when undated. Absent from older servers. */
    age_days?: number | null;
    /** The configured NAV age limit, in days. */
    max_age_days?: number | null;
    /** Only a "current" NAV's premium/discount is reliable. */
    status?: NavStatus | null;
  };
  income: {
    dividend_yield: number | null;
    payout_ratio: number | null;
    dividend_cover: number | null;
  };
  balance_sheet: {
    currency: string | null;
    total_debt: number | null;
    total_cash: number | null;
    net_debt: number | null;
    net_gearing: number | null;
    /** Percent, as Yahoo reports it (45.4 = 45.4%). */
    debt_to_equity: number | null;
  };
  benchmark: { ticker: string; name: string | null; source: string };
  risk: {
    volatility_1y: number | null;
    beta_3y: number | null;
    beta_weeks: number | null;
    beta_provider: number | null;
    max_drawdown: number | null;
    max_drawdown_peak: string | null;
    max_drawdown_trough: string | null;
    history_start: string | null;
    history_end: string | null;
    history_years: number | null;
  };
  data_quality: {
    price_last_date: string | null;
    price_stale: boolean | null;
    suspect_moves: { date: string; change: number }[];
    warnings: string[];
    price_snapshot?: { is_stale: boolean | null; last_price_date: string | null };
  };
}

/**
 * Technical indicators from GET /screener/technicals, computed from daily closes.
 * Percentages are fractions (0.05 = 5%); price levels are in the quote's units.
 * An indicator without enough history is null.
 */
export interface InstrumentTechnicals {
  ticker: string;
  name: string | null;
  price: number | null;
  price_currency: string | null;
  as_of: string | null;
  moving_averages: {
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    vs_sma_20: number | null;
    vs_sma_50: number | null;
    vs_sma_200: number | null;
    /** "uptrend" | "downtrend" | "mixed" */
    trend: string | null;
    /** "golden" | "death" */
    cross_state: string | null;
    last_cross: string | null;
    last_cross_date: string | null;
  };
  rsi: {
    value: number | null;
    period: number;
    /** "overbought" | "oversold" | "neutral" */
    zone: string | null;
  };
  macd: {
    macd: number | null;
    signal: number | null;
    histogram: number | null;
    /** "bullish" | "bearish" */
    last_crossover: string | null;
    last_crossover_date: string | null;
  };
  bollinger: {
    upper: number | null;
    middle: number | null;
    lower: number | null;
    /** 0 = lower band, 1 = upper band. */
    percent_b: number | null;
    bandwidth: number | null;
  };
  range_52w: {
    high: number | null;
    high_date: string | null;
    low: number | null;
    low_date: string | null;
    /** 0 = at the low, 1 = at the high. */
    position: number | null;
    from_high: number | null;
  };
  returns: Record<string, number | null>;
  relative_strength: {
    benchmark: { ticker: string; name: string | null; source: string };
    excess_3m: number | null;
    excess_1y: number | null;
  };
  signals: string[];
  data_quality: {
    price_last_date: string | null;
    price_stale: boolean | null;
    data_points: number;
    warnings: string[];
  };
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

export type TrailAnalyticsEvent = "view" | "task_started" | "task_completed";
export type VirtualPortfolioAnalyticsEvent =
  | "view"
  | "create"
  | "update"
  | "delete"
  | "select";

export type AnalyticsSource = "trail" | "virtual_portfolio";
export type AnalyticsEventName =
  | TrailAnalyticsEvent
  | VirtualPortfolioAnalyticsEvent;

export interface AnalyticsEventPayload {
  source: AnalyticsSource;
  event: AnalyticsEventName;
  metadata?: Record<string, unknown>;
  occurred_at?: string;
  user?: string | null;
}

export interface AnalyticsFunnelStep {
  event: string;
  count: number;
}

export interface AnalyticsFunnelSummary {
  source: AnalyticsSource;
  total_events: number;
  unique_users: number;
  first_event_at: string | null;
  last_event_at: string | null;
  steps: AnalyticsFunnelStep[];
  other_events?: Record<string, number> | null;
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
  factors?: string[];
  /**
   * Names of compliance/screening checks that were skipped because
   * allotmint-pro is not installed, e.g. ["compliance", "fundamental_screen"].
   * Empty (or absent) when every applicable check ran.
   */
  checks_skipped?: string[];
}

export interface TradingAgentSettings {
  rsi_buy: number | null;
  rsi_sell: number | null;
  rsi_window: number;
  ma_short_window: number;
  ma_long_window: number;
  pe_max: number | null;
  de_max: number | null;
  min_sharpe: number | null;
  max_volatility: number | null;
}

export interface TradingPageData {
  signals: TradingSignal[];
  settings: TradingAgentSettings;
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

/**
 * Per-owner targets (percent) and drift band (pp). Keys are asset classes or,
 * for Bond/Commodity, sub-classes such as "long_gilts" or "gold" (#9543).
 */
export interface AllocationPolicy {
  targets: Record<string, number>;
  tolerance_pct: number;
}

export interface RebalanceClassRow {
  /** Asset class or sub-class key the row is bucketed by. */
  asset_class: string;
  /**
   * Parent class of a sub-class row; equal to ``asset_class`` on a split
   * class's "no sub-class" row; null/absent on whole-class rows.
   */
  parent?: string | null;
  label: string;
  current_value: number;
  current_pct: number;
  target_pct: number | null;
  drift_pct: number | null;
  in_band: boolean | null;
}

export interface RebalanceTrade {
  account_id: string;
  account: string;
  asset_class: string;
  action: "buy" | "sell";
  amount: number;
  ticker: string | null;
  /** Display name of the suggested instrument, when the holding has one. */
  name: string | null;
}

export interface RebalanceAccount {
  id: string;
  label: string;
  value: number;
  cash: number;
}

/** Current weight of a held sub-class, reported whatever the policy level. */
export interface RebalanceSubClassRow {
  asset_class: string;
  parent: string;
  label: string;
  current_value: number;
  current_pct: number;
}

export interface RebalancePlan {
  policy: AllocationPolicy;
  total_value: number;
  classes: RebalanceClassRow[];
  sub_classes?: RebalanceSubClassRow[];
  unclassified_value: number;
  unclassified_pct: number;
  unpriced_tickers: string[];
  accounts: RebalanceAccount[];
  trades: RebalanceTrade[];
  unfunded_amount: number;
  notes: string[];
}

export interface NewCashPlan {
  account_id: string;
  account: string;
  trades: RebalanceTrade[];
  keep_as_cash: number;
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

export type ReportTemplateFilterOperator =
  | "equals"
  | "not_equals"
  | "contains"
  | "gt"
  | "lt";

export interface ReportTemplateFilter {
  field: string;
  operator: ReportTemplateFilterOperator;
  value: string;
}

export interface ReportTemplateColumnMetadata {
  key: string;
  label: string;
  type: string;
}

export interface ReportTemplateSectionMetadata {
  id: string;
  title: string;
  description?: string | null;
  source: string;
  columns: ReportTemplateColumnMetadata[];
}

export interface ReportTemplateMetadata {
  template_id: string;
  name: string;
  description?: string | null;
  builtin: boolean;
  sections: ReportTemplateSectionMetadata[];
}

export interface ReportTemplate {
  id: string;
  name: string;
  metrics: string[];
  columns: string[];
  filters: ReportTemplateFilter[];
  description?: string | null;
  updated_at?: string | null;
  optimistic?: boolean;
}

export interface ReportTemplateInput {
  name: string;
  metrics: string[];
  columns: string[];
  filters: ReportTemplateFilter[];
  description?: string | null;
}
