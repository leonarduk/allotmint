export type OwnerSummary = {
  owner: string;
  accounts: string[];
};

export interface Holding {
  ticker: string;
  name: string;
  units: number;
  acquired_date: string;
  price?: number;
  cost_basis_gbp?: number;
  market_value_gbp?: number;
  gain_gbp?: number;
  current_price_gbp?: number | null;

  // Add these:
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
  group: string;      // "children" | "adults" | "all" | …
  name: string;      // "Children" | "Adults" | "All"
  members: string[]; // ["alex", "joe"] etc.
};

export type GroupPortfolio = {
  /* identification */
  group: string;
  name: string;           // display label ("Children")

  /* snapshot */
  as_of: string;
  members: string[];

  /* totals */
  total_value_estimate_gbp: number;
  trades_this_month?: number;
  trades_remaining?: number;

  /* aggregated detail */
  accounts: Account[];    // ← used by GroupPortfolioView
  members_summary: {
    owner: string;
    total_value_estimate_gbp: number;
    trades_this_month: number;
    trades_remaining: number;
  }[];

  subtotals_by_account_type: Record<string, number>;
};

