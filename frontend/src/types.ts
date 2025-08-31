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
    effective_cost_basis_gbp?: number;
    market_value_gbp?: number;
    gain_gbp?: number;
    gain_pct?: number;
    current_price_gbp?: number | null;
    /** Date of the last known price for this holding */
    last_price_date?: string | null;
    latest_source?: string | null;
    day_change_gbp?: number;
    instrument_type?: string | null;

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
    holdings: Holding[];
    owner?: string;
};

export type Portfolio = {
    owner: string;
    as_of: string;
    trades_this_month: number;
    trades_remaining: number;
    total_value_estimate_gbp: number;
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
    trades_this_month?: number;
    trades_remaining?: number;
    accounts: Account[];
    members_summary: {
        owner: string;
        total_value_estimate_gbp: number;
        trades_this_month: number;
        trades_remaining: number;
    }[];
    subtotals_by_account_type: Record<string, number>;
};

export type InstrumentSummary = {
    ticker: string;
    name: string;
    currency?: string | null;
    units: number;
    market_value_gbp: number;
    gain_gbp: number;
    instrument_type?: string | null;
    gain_pct?: number;

    /* last-price enrichment */
    last_price_gbp?: number | null;
    last_price_date?: string | null;
    change_7d_pct?: number | null;
    change_30d_pct?: number | null;
};

export type SectorContribution = {
    sector: string;
    market_value_gbp: number;
    gain_gbp: number;
    cost_gbp: number;
    gain_pct?: number | null;
    contribution_pct?: number | null;
};

export type RegionContribution = {
    region: string;
    market_value_gbp: number;
    gain_gbp: number;
    cost_gbp: number;
    gain_pct?: number | null;
    contribution_pct?: number | null;
};

export interface PerformancePoint {
    date: string;
    value: number;
    daily_return?: number | null;
    weekly_return?: number | null;
    cumulative_return?: number | null;
}

export interface ValueAtRiskPoint {
    date: string;
    var: number;
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

  
export interface InstrumentDetailMini {
    [range: string]: {
        date: string;
        close: number;
        close_gbp: number;
    }[];
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
    shares?: number | null;
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
    time: string | null;
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

export interface ScenarioResult {
    owner: string;
    total_value_estimate_gbp: number;
}

export type ComplianceResult = {
    owner: string;
    warnings: string[];
    trade_counts: Record<string, number>;
};

export interface ScreenerResult {
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
    action: string;
    reason: string;
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
};

export interface TradeSuggestion {
    ticker: string;
    action: string;
    amount: number;
}

