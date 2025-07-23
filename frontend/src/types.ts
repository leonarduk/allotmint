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
  group: string;
  members: string[];
};

export type GroupPortfolio = {
  group: string;
  as_of: string;
  members: string[];
  total_value_estimate_gbp: number;
  members_summary: {
    owner: string;
    total_value_estimate_gbp: number;
    trades_this_month: number;
    trades_remaining: number;
  }[];
  subtotals_by_account_type: Record<string, number>;
};

export type Holding = {
  ticker: string;
  name?: string;
  units: number;
  cost_basis_gbp?: number;
  acquired_date?: string;
  days_held?: number | null;
  sell_eligible?: boolean;
  eligible_on?: string | null;
  days_until_eligible?: number | null;
  current_price_gbp?: number | null;
  market_value_gbp?: number | null;
  unrealized_gain_gbp?: number | null;
};
