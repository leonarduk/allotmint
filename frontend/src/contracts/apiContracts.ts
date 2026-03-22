import { z } from "zod";

export const API_CONTRACT_VERSION = "v1" as const;

const nullableString = z.string().nullable();
const nullableNumber = z.number().nullable();

export const configContractSchema = z.object({
  app_name: z.string(),
  app_env: z.string(),
  demo_mode: z.boolean(),
  theme: z.string(),
  tabs: z.record(z.string(), z.boolean()),
  disabled_tabs: z.array(z.string()),
  ui: z.object({
    theme: z.string(),
    relative_view_enabled: z.boolean(),
    tabs: z.record(z.string(), z.boolean()),
  }),
  auth: z.object({
    google_auth_enabled: z.boolean().nullable(),
    google_client_id: nullableString,
    disable_auth: z.boolean(),
    allowed_emails: z.array(z.string()),
    local_login_email: nullableString,
  }),
}).passthrough();

export const ownerSummarySchema = z.object({
  owner: z.string(),
  full_name: z.string(),
  accounts: z.array(z.string()),
  email: nullableString.optional(),
  has_transactions_artifact: z.boolean(),
});

export const ownersContractSchema = z.array(ownerSummarySchema);

export const groupsContractSchema = z.array(z.object({
  slug: z.string(),
  name: z.string(),
  members: z.array(z.string()),
}));

export const holdingContractSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  currency: nullableString.optional(),
  units: z.number(),
  acquired_date: z.string(),
  price: z.number().optional(),
  cost_basis_gbp: z.number().optional(),
  cost_basis_currency: nullableString.optional(),
  effective_cost_basis_gbp: z.number().optional(),
  effective_cost_basis_currency: nullableString.optional(),
  market_value_gbp: z.number().optional(),
  market_value_currency: nullableString.optional(),
  gain_gbp: z.number().optional(),
  gain_currency: nullableString.optional(),
  gain_pct: z.number().optional(),
  current_price_gbp: nullableNumber.optional(),
  current_price_currency: nullableString.optional(),
  last_price_date: nullableString.optional(),
  last_price_time: nullableString.optional(),
  is_stale: z.boolean().optional(),
  latest_source: nullableString.optional(),
  day_change_gbp: z.number().optional(),
  day_change_currency: nullableString.optional(),
  instrument_type: nullableString.optional(),
  sector: nullableString.optional(),
  region: nullableString.optional(),
  forward_7d_change_pct: nullableNumber.optional(),
  forward_30d_change_pct: nullableNumber.optional(),
  days_held: z.number().optional(),
  sell_eligible: z.boolean().optional(),
  days_until_eligible: nullableNumber.optional(),
  next_eligible_sell_date: nullableString.optional(),
});

export const accountContractSchema = z.object({
  owner: z.string().optional(),
  account_type: z.string(),
  currency: z.string(),
  last_updated: z.string().optional(),
  value_estimate_gbp: z.number(),
  value_estimate_currency: nullableString.optional(),
  holdings: z.array(holdingContractSchema),
});

export const portfolioContractSchema = z.object({
  owner: z.string(),
  as_of: z.string(),
  trades_this_month: z.number(),
  trades_remaining: z.number(),
  total_value_estimate_gbp: z.number(),
  total_value_estimate_currency: nullableString.optional(),
  accounts: z.array(accountContractSchema),
});

export const transactionContractSchema = z.object({
  owner: z.string(),
  account: z.string(),
  id: nullableString.optional(),
  date: nullableString.optional(),
  ticker: nullableString.optional(),
  type: nullableString.optional(),
  kind: nullableString.optional(),
  amount_minor: nullableNumber.optional(),
  currency: nullableString.optional(),
  security_ref: nullableString.optional(),
  price_gbp: nullableNumber.optional(),
  price: nullableNumber.optional(),
  shares: nullableNumber.optional(),
  units: nullableNumber.optional(),
  fees: nullableNumber.optional(),
  comments: nullableString.optional(),
  reason: nullableString.optional(),
  reason_to_buy: nullableString.optional(),
  synthetic: z.boolean(),
  instrument_name: nullableString.optional(),
});

export const transactionsContractSchema = z.array(transactionContractSchema);
