export type OwnerSummary = {
  owner: string;
  accounts: string[];
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
};

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
