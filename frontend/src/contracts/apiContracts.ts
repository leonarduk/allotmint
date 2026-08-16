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
  // price/cost_basis_gbp/effective_cost_basis_gbp/market_value_gbp/gain_gbp/
  // gain_pct are nullable: backend/common/holding_utils.py legitimately
  // returns null for all of these when a holding has zero units or an
  // unresolvable price (see the units<=0 and price-unresolved branches of
  // enrich_holding), so treating them as always-a-number makes
  // portfolioContractSchema.parse() throw on real accounts.
  price: nullableNumber.optional(),
  cost_basis_gbp: nullableNumber.optional(),
  cost_basis_currency: nullableString.optional(),
  effective_cost_basis_gbp: nullableNumber.optional(),
  effective_cost_basis_currency: nullableString.optional(),
  market_value_gbp: nullableNumber.optional(),
  market_value_currency: nullableString.optional(),
  gain_gbp: nullableNumber.optional(),
  gain_currency: nullableString.optional(),
  gain_pct: nullableNumber.optional(),
  current_price_gbp: nullableNumber.optional(),
  current_price_currency: nullableString.optional(),
  last_price_date: nullableString.optional(),
  last_price_time: nullableString.optional(),
  is_stale: z.boolean().optional(),
  latest_source: nullableString.optional(),
  day_change_gbp: nullableNumber.optional(),
  day_change_currency: nullableString.optional(),
  instrument_type: nullableString.optional(),
  sector: nullableString.optional(),
  region: nullableString.optional(),
  forward_7d_change_pct: nullableNumber.optional(),
  forward_30d_change_pct: nullableNumber.optional(),
  days_held: nullableNumber.optional(),
  sell_eligible: z.boolean().optional(),
  days_until_eligible: nullableNumber.optional(),
  next_eligible_sell_date: nullableString.optional(),
  eligible_on: nullableString.optional(),
  cost_basis_source: nullableString.optional(),
  asset_class: nullableString.optional(),
  unrealised_gain_gbp: nullableNumber.optional(),
  unrealized_gain_gbp: nullableNumber.optional(),
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
// it identifies itself with `slug` + `name` + `members` rather than `owner`,
// and carries members_summary / subtotals_by_account_type that Portfolio does
// not have.  Using portfolioContractSchema here would throw at runtime because
// `owner` is required there but absent in group portfolio responses.
export const groupPortfolioContractSchema = z.object({
  slug: z.string(),
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
  ).optional(),
  subtotals_by_account_type: z.record(z.string(), z.number()).optional(),
});

export const transactionContractSchema = z.object({
  owner: z.string(),
  account: z.string(),
  id: nullableString.optional(),
  external_id: nullableString.optional(),
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

const dataQualityGapPeriodSchema = z.object({
  start: z.string(),
  end: z.string(),
  missing_business_days: z.number(),
});

const dataQualityOutlierSchema = z.object({
  date: z.string(),
  value: z.number(),
  z_score: z.number(),
});

const timeseriesQualityPositionSchema = z.object({
  ticker: z.string(),
  exchange: z.string(),
  total_points: z.number(),
  first_date: nullableString,
  last_date: nullableString,
  gap_count: z.number(),
  gaps: z.array(dataQualityGapPeriodSchema),
  duplicate_dates: z.array(z.string()),
  outliers: z.array(dataQualityOutlierSchema),
});

export const dataQualityTimeseriesContractSchema = z.object({
  count: z.number(),
  positions: z.array(timeseriesQualityPositionSchema),
});

// ───────────── Data Quality Admin (read-write) ─────────────

const dataQualityIssueSchema = z.object({
  id: z.string(),
  type: z.string(),
  severity: z.enum(["high", "medium", "low"]),
  entity: z.record(z.string(), z.unknown()),
  description: z.string(),
  suggested_fix: z.string(),
  preview: z.record(z.string(), z.unknown()),
  fixable: z.boolean(),
});

export const dataQualityIssuesContractSchema = z.object({
  count: z.number(),
  issues: z.array(dataQualityIssueSchema),
});

export const dataQualityAuditContractSchema = z.object({
  count: z.number(),
  entries: z.array(
    z.object({
      id: z.string(),
      timestamp: z.string(),
      action: z.string(),
      issue_id: z.string(),
      entity: z.record(z.string(), z.unknown()),
      before: z.record(z.string(), z.unknown()),
      after: z.record(z.string(), z.unknown()),
      actor: nullableString,
    }),
  ),
});

export const apiContractSchemas = {
  config: configContractSchema,
  owners: ownersContractSchema,
  groups: groupsContractSchema,
  groupPortfolio: groupPortfolioContractSchema,
  portfolio: portfolioContractSchema,
  transactions: transactionsContractSchema,
  dataQualityTimeseries: dataQualityTimeseriesContractSchema,
  dataQualityIssues: dataQualityIssuesContractSchema,
  dataQualityAudit: dataQualityAuditContractSchema,
} as const;

// satisfies Record<keyof typeof apiContractSchemas, object> enforces that every
// key present in apiContractSchemas also appears here, so adding a new schema
// to one without updating the other is a compile-time error.  We use `object`
// rather than `ReturnType<typeof toJSONSchema>` because zod 4.4.x exposes
// toJSONSchema as an overloaded function whose union return type includes a
// `{ schemas: ... }` variant that doesn't match the single-schema call site.
export const apiContractJsonSchemas = {
  config: toJSONSchema(configContractSchema),
  owners: toJSONSchema(ownersContractSchema),
  groups: toJSONSchema(groupsContractSchema),
  groupPortfolio: toJSONSchema(groupPortfolioContractSchema),
  portfolio: toJSONSchema(portfolioContractSchema),
  transactions: toJSONSchema(transactionsContractSchema),
  dataQualityTimeseries: toJSONSchema(dataQualityTimeseriesContractSchema),
  dataQualityIssues: toJSONSchema(dataQualityIssuesContractSchema),
  dataQualityAudit: toJSONSchema(dataQualityAuditContractSchema),
} satisfies Record<keyof typeof apiContractSchemas, object>;
