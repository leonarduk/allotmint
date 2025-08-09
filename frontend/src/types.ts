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
    day_change_gbp?: number;
    currency?: string;
    instrument_type?: string | null;

    days_held?: number;
    sell_eligible?: boolean;
    days_until_eligible?: number | null;
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
    currency?: string;
    instrument_type?: string | null;
    gain_pct?: number;

    /* last-price enrichment */
    last_price_gbp?: number | null;
    last_price_date?: string | null;
    change_7d_pct?: number | null;
    change_30d_pct?: number | null;
};

export interface PerformancePoint {
    date: string;
    value: number;
    daily_return?: number | null;
    weekly_return?: number | null;
    cumulative_return?: number | null;
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

export type Alert = {
    ticker: string;
    change_pct: number;
    message: string;
    timestamp: string;
};

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
    fcf: number | null;
}

