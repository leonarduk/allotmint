import { z } from "zod";

export const SPA_RESPONSE_CONTRACT_VERSION = "2026-03-22";

const nullableString = z.string().nullable().optional();
const nullableNumber = z.number().nullable().optional();
const nullableBoolean = z.boolean().nullable().optional();

export const configTabsContractSchema = z
  .object({
    portfolio: z.boolean(),
    transactions: z.boolean(),
    goals: z.boolean(),
    tax: z.boolean(),
    alerts: z.boolean(),
    performance: z.boolean(),
    wizard: z.boolean(),
    ideas: z.boolean(),
    reports: z.boolean(),
    settings: z.boolean(),
    queries: z.boolean(),
    compliance: z.boolean(),
    "trade-compliance": z.boolean(),
    pension: z.boolean(),
  })
  .strict();

export const configContractSchema = z
  .object({
    app_env: z.string(),
    google_auth_enabled: z.boolean().nullable().optional(),
    google_client_id: nullableString,
    disable_auth: z.boolean(),
    local_login_email: nullableString,
    allowed_emails: z.array(z.string()).nullable().optional(),
    theme: nullableString,
    relative_view_enabled: nullableBoolean,
    base_currency: nullableString,
    tabs: configTabsContractSchema,
    disabled_tabs: z.array(z.string()),
  })
  .strict();

export const ownerSummaryContractSchema = z
  .object({
    owner: z.string(),
    full_name: z.string(),
    accounts: z.array(z.string()),
    email: nullableString,
    has_transactions_artifact: z.boolean().optional().default(false),
  })
  .strict();

export const groupSummaryContractSchema = z
  .object({ slug: z.string(), name: z.string(), members: z.array(z.string()) })
  .strict();

export const holdingContractSchema = z
  .object({
    ticker: z.string(),
    name: z.string(),
    units: z.number(),
    acquired_date: z.string(),
    currency: nullableString,
    price: nullableNumber,
    cost_basis_gbp: nullableNumber,
    cost_basis_currency: nullableString,
    effective_cost_basis_gbp: nullableNumber,
    effective_cost_basis_currency: nullableString,
    market_value_gbp: nullableNumber,
    market_value_currency: nullableString,
    gain_gbp: nullableNumber,
    gain_currency: nullableString,
    gain_pct: nullableNumber,
    current_price_gbp: nullableNumber,
    current_price_currency: nullableString,
    last_price_date: nullableString,
    last_price_time: nullableString,
    is_stale: nullableBoolean,
    latest_source: nullableString,
    day_change_gbp: nullableNumber,
    day_change_currency: nullableString,
    instrument_type: nullableString,
    sector: nullableString,
    region: nullableString,
    forward_7d_change_pct: nullableNumber,
    forward_30d_change_pct: nullableNumber,
    days_held: z.number().int().nullable().optional(),
    sell_eligible: nullableBoolean,
    days_until_eligible: z.number().int().nullable().optional(),
    next_eligible_sell_date: nullableString,
  })
  .strict();

export const accountContractSchema = z
  .object({
    account_type: z.string(),
    currency: z.string(),
    last_updated: nullableString,
    value_estimate_gbp: z.number(),
    value_estimate_currency: nullableString,
    holdings: z.array(holdingContractSchema),
    owner: nullableString,
  })
  .strict();

export const portfolioContractSchema = z
  .object({
    owner: z.string(),
    as_of: z.string(),
    trades_this_month: z.number().int(),
    trades_remaining: z.number().int(),
    total_value_estimate_gbp: z.number(),
    total_value_estimate_currency: nullableString,
    accounts: z.array(accountContractSchema),
  })
  .strict();

export const transactionContractSchema = z
  .object({
    owner: z.string(),
    account: z.string(),
    id: nullableString,
    date: nullableString,
    ticker: nullableString,
    type: nullableString,
    kind: nullableString,
    amount_minor: nullableNumber,
    currency: nullableString,
    security_ref: nullableString,
    price_gbp: nullableNumber,
    price: nullableNumber,
    shares: nullableNumber,
    units: nullableNumber,
    fees: nullableNumber,
    comments: nullableString,
    reason: nullableString,
    reason_to_buy: nullableString,
    synthetic: z.boolean().optional().default(false),
    instrument_name: nullableString,
  })
  .strict();

export const spaContractEnvelopeSchema = z
  .object({
    version: z.literal(SPA_RESPONSE_CONTRACT_VERSION),
    config: configContractSchema,
    owners: z.array(ownerSummaryContractSchema),
    groups: z.array(groupSummaryContractSchema),
    portfolio: portfolioContractSchema,
    transactions: z.array(transactionContractSchema),
  })
  .strict();
