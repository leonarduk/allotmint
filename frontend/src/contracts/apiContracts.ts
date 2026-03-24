import { toJSONSchema, z } from "zod";

export const API_CONTRACT_VERSION = "v1" as const;

const nullableString = z.string().nullable();
const nullableNumber = z.number().nullable();
const tabsSchema = z.record(z.string(), z.boolean());

// .passthrough() is intentional: /config is allowed to carry additional
// backend-only fields (feature flags, env-specific keys, etc.) that the
// frontend does not need to enumerate.  Tightening to .strict() here would
// cause runtime failures whenever the backend adds a new config key before
// the frontend schema is updated.  The required fields below remain
// enforced; only unexpected extra fields are passed through silently.
export const configContractSchema = z
  .object({
    app_env: z.string(),
    theme: z.string().nullable(),
    tabs: tabsSchema,
    relative_view_enabled: z.boolean().nullable(),
    google_auth_enabled: z.boolean().nullable(),
    google_client_id: nullableString,
    disable_auth: z.boolean(),
    allowed_emails: z.array(z.string()).nullable(),
    local_login_email: nullableString,
    disabled_tabs: z.array(z.string()).nullable().optional(),
  })
  .passthrough();

export const ownerSummarySchema = z.object({
  owner: z.string(),
  full_name: z.string(),
  accounts: z.array(z.string()),
  email: nullableString.optional(),
  has_transactions_artifact: z.boolean(),
});

export const ownersContractSchema = z.array(ownerSummarySchema);

export const groupsContractSchema = z.array(
  z.object({
    slug: z.string(),
    name: z.string(),
    members: z.array(z.string()),
  }),
);

export const holdingContractSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  currency: nullableString.optional(),
  units: z.number(),
  // acquired_date is optional/nullable: cash positions and some older holdings
  // may not carry an acquisition date.  Making this required would throw at
  // runtime and break the portfolio view for those records.
  acquired_date: z.string().nullable().optional(),
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
  last_updated: z.string().nullable().optional(),
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

// GroupPortfolio has a different top-level shape from Portfolio:
// it identifies itself with `group` + `name` + `members` rather than `owner`,
// and carries members_summary / subtotals_by_account_type that Portfolio does
// not have.  Using portfolioContractSchema here would throw at runtime because
// `owner` is required there but absent in group portfolio responses.
export const groupPortfolioContractSchema = z.object({
  group: z.string(),
  name: z.string(),
  as_of: z.string(),
  members: z.array(z.string()),
  total_value_estimate_gbp: z.number(),
  total_value_estimate_currency: nullableString.optional(),
  trades_this_month: z.number().optional(),
  trades_remaining: z.number().optional(),
  accounts: z.array(accountContractSchema),
  members_summary: z.array(
    z.object({
      owner: z.string(),
      total_value_estimate_gbp: z.number(),
      total_value_estimate_currency: nullableString.optional(),
      trades_this_month: z.number(),
      trades_remaining: z.number(),
    }),
  ),
  subtotals_by_account_type: z.record(z.string(), z.number()),
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
  // synthetic defaults to false: older records and some backends may omit this
  // field entirely.  A required boolean would throw at runtime for those rows,
  // breaking the transactions view.  The .default(false) keeps callers
  // receiving a boolean without needing to handle undefined.
  synthetic: z.boolean().default(false),
  instrument_name: nullableString.optional(),
});

export const transactionsContractSchema = z.array(transactionContractSchema);

export const apiContractSchemas = {
  config: configContractSchema,
  owners: ownersContractSchema,
  groups: groupsContractSchema,
  portfolio: portfolioContractSchema,
  transactions: transactionsContractSchema,
} as const;

export const apiContractJsonSchemas = Object.fromEntries(
  Object.entries(apiContractSchemas).map(([name, schema]) => [name, toJSONSchema(schema)]),
) as Record<keyof typeof apiContractSchemas, ReturnType<typeof toJSONSchema>>;
