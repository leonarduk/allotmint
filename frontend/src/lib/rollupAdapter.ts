import type { Account, Holding, InstrumentSummary } from "../types";
import { COST_BASIS_UNKNOWN, isCostBasisUnreliable } from "./costBasis";

export type ScopedHoldingRow = Holding & {
  owner: string;
  source_account: string;
  row_key: string;
};

export type RollupRow = {
  ticker: string;
  name: string;
  units: number;
  cost_basis_gbp: number;
  effective_cost_basis_gbp: number;
  market_value_gbp: number;
  // Null when no lot has a known cost, so the gain is unknown (#8471).
  gain_gbp: number | null;
  gain_pct: number | null;
  // "unknown" when no lot has a known cost (zero, guessed or book_suspect);
  // mirrors Holding (#8471). A ticker mixing known- and unknown-cost lots gets
  // null: its gain/gain_pct come from the known lots only, but
  // effective_cost_basis_gbp still includes the unknown lots' cost.
  cost_basis_source?: "unknown" | null;
  weight_pct: number;
  lot_count: number;
  owners: string[];
  accounts: string[];
  grouping: string | null;
  sector: string | null;
  exchange: string | null;
  change_7d_pct: number | null;
  change_30d_pct: number | null;
  // Describe the oldest lot in the group: its acquisition date is the
  // earliest date among the lots, days held is recalculated against the
  // portfolio snapshot passed to toRollupRows, and its eligibility metadata
  // is retained as-is. A ticker with no lot carrying a valid acquired_date
  // falls back to null (genuinely unknown), which the table renders as an
  // explicit "N/A"/"—" rather than a silently wrong value.
  acquired_date: string | null;
  days_held: number | null;
  sell_eligible: boolean | null;
  days_until_eligible: number | null;
  next_eligible_sell_date: string | null;
  // Per-unit/descriptive fields that are expected to be identical across all
  // lots of the same ticker (price is per-unit, not per-lot; currency and
  // instrument type are properties of the instrument, not the position). Take
  // them from the first lot encountered for the ticker — mirrors how
  // acquired_date/eligibility are sourced from a representative lot rather
  // than re-derived per-field. Genuinely missing on that lot falls back to
  // null (renders as "N/A"/"—"), matching the existing pattern.
  current_price_gbp: number | null;
  current_price_currency: string | null;
  currency: string | null;
  instrument_type: string | null;
  // Income and total return summed over the ticker's lots (#9038). Absent when
  // no lot carries them (cash); null when any lot's figure is unknown, so a
  // partial sum is never shown as the whole position's.
  income_gbp?: number | null;
  income_estimated?: boolean | null;
  realised_gain_gbp?: number | null;
  total_return_gbp?: number | null;
  total_return_pct?: number | null;
  yield_pct?: number | null;
};

// Running income/total-return sums for one ticker's lots. A field becomes null
// once any lot reports it unknown; `undefined` means no lot carried it.
type ReturnSums = {
  income: number | null | undefined;
  incomeEstimated: boolean;
  realised: number | null | undefined;
  total: number | null | undefined;
  // Cost ever put in, recovered per lot from total / pct; null when a lot's
  // percentage is unknown, so the combined percentage is too.
  invested: number | null;
  trailingIncome: number;
  hasYield: boolean;
};

const addKnown = (
  sum: number | null | undefined,
  value: number | null | undefined,
): number | null | undefined => {
  if (value === undefined) return sum;
  if (value === null || sum === null) return null;
  return (sum ?? 0) + value;
};

// The cost behind a lot's total_return_pct (total / pct). A zero total gives
// no ratio, so fall back to the cost behind its capital gain (market - gain),
// which misses only the cost of units already sold.
function lotInvested(holding: Holding): number | null {
  const total = holding.total_return_gbp;
  const pct = holding.total_return_pct;
  if (total == null || pct == null) return null;
  if (pct !== 0) return total / (pct / 100);
  return (holding.market_value_gbp ?? 0) - (holding.gain_gbp ?? 0);
}

function emptyReturnSums(): ReturnSums {
  return {
    income: undefined,
    incomeEstimated: false,
    realised: undefined,
    total: undefined,
    invested: 0,
    trailingIncome: 0,
    hasYield: false,
  };
}

function addLotReturns(sums: ReturnSums, holding: Holding): void {
  sums.income = addKnown(sums.income, holding.income_gbp);
  sums.incomeEstimated = sums.incomeEstimated || holding.income_estimated === true;
  sums.realised = addKnown(sums.realised, holding.realised_gain_gbp);
  sums.total = addKnown(sums.total, holding.total_return_gbp);
  if (holding.total_return_gbp !== undefined) {
    const invested = lotInvested(holding);
    sums.invested =
      sums.invested === null || invested === null ? null : sums.invested + invested;
  }
  if (holding.yield_pct != null) {
    sums.trailingIncome += (holding.yield_pct / 100) * (holding.market_value_gbp ?? 0);
    sums.hasYield = true;
  }
}

type RollupReturns = Pick<
  RollupRow,
  | "income_gbp"
  | "income_estimated"
  | "realised_gain_gbp"
  | "total_return_gbp"
  | "total_return_pct"
  | "yield_pct"
>;

function finishReturns(sums: ReturnSums, marketValue: number): RollupReturns {
  // No lot carried the fields (cash): leave them absent, as on the lots.
  if (sums.total === undefined && sums.income === undefined) return {};
  const total = sums.total ?? null;
  return {
    income_gbp: sums.income ?? null,
    income_estimated: sums.incomeEstimated,
    realised_gain_gbp: sums.realised ?? null,
    total_return_gbp: total,
    total_return_pct:
      total !== null && sums.invested !== null && sums.invested > 0
        ? (total / sums.invested) * 100
        : null,
    // Trailing income over the whole position's value, not an average of yields.
    yield_pct:
      sums.hasYield && marketValue > 0 ? (sums.trailingIncome / marketValue) * 100 : null,
  };
}

export function toScopedHoldingRows(accounts: Account[]): ScopedHoldingRow[] {
  let rowIndex = 0;

  return accounts.flatMap((account) => {
    const owner = account.owner ?? "";

    return account.holdings.map((holding) => {
      const row = {
        ...holding,
        owner,
        source_account: account.account_type,
        row_key: `${owner}:${account.account_type}:${holding.ticker}:${rowIndex}`,
      };
      rowIndex += 1;
      return row;
    });
  });
}

type MutableRollup = Omit<
  RollupRow,
  | "weight_pct"
  | "grouping"
  | "sector"
  | "exchange"
  | "change_7d_pct"
  | "change_30d_pct"
  | "gain_gbp"
  | "gain_pct"
  | "cost_basis_source"
  | keyof RollupReturns
> & {
  // Gain and cost summed over lots with a known cost only (#8471).
  gain_gbp: number;
  gainCost: number;
  hasKnownGain: boolean;
  returns: ReturnSums;
  ownerSet: Set<string>;
  accountSet: Set<string>;
  oldestLot: ScopedHoldingRow;
};

const hasValidAcquiredDate = (lot: ScopedHoldingRow): boolean =>
  !!lot.acquired_date && !Number.isNaN(Date.parse(lot.acquired_date));

// True when `candidate` was acquired earlier than `current` (or is the only
// one of the two with a usable acquired_date).
const isEarlierAcquisition = (
  candidate: ScopedHoldingRow,
  current: ScopedHoldingRow,
): boolean => {
  if (!hasValidAcquiredDate(candidate)) return false;
  if (!hasValidAcquiredDate(current)) return true;
  return Date.parse(candidate.acquired_date!) < Date.parse(current.acquired_date!);
};

function addHolding(
  grouped: Map<string, MutableRollup>,
  holding: ScopedHoldingRow,
): void {
  // Mirror HoldingsTable's per-row cost fallback so a lot whose cost is
  // derived (effective_cost_basis_gbp) rather than booked still contributes
  // its cost to the rollup. Without this, positions without a booked cost
  // basis roll up to £0.00 cost and a gain % of 0 (or an absurd total %).
  const holdingCost =
    (holding.cost_basis_gbp ?? 0) > 0
      ? holding.cost_basis_gbp ?? 0
      : holding.effective_cost_basis_gbp ?? 0;
  // A zero cost or the last-resort guessed cost (#7220) has no real gain.
  const gainKnown =
    holding.gain_gbp != null &&
    !isCostBasisUnreliable(holding.cost_basis_source) &&
    holdingCost > 0;
  const lotGain = gainKnown ? holding.gain_gbp ?? 0 : 0;
  const lotGainCost = gainKnown ? holdingCost : 0;

  const existing = grouped.get(holding.ticker);
  if (existing) {
    existing.units += holding.units;
    existing.cost_basis_gbp += holding.cost_basis_gbp ?? 0;
    existing.effective_cost_basis_gbp += holdingCost;
    existing.market_value_gbp += holding.market_value_gbp ?? 0;
    existing.gain_gbp += lotGain;
    existing.gainCost += lotGainCost;
    existing.hasKnownGain = existing.hasKnownGain || gainKnown;
    existing.lot_count += 1;
    addLotReturns(existing.returns, holding);
    existing.ownerSet.add(holding.owner);
    existing.accountSet.add(holding.source_account);
    if (isEarlierAcquisition(holding, existing.oldestLot)) {
      existing.oldestLot = holding;
    }
    return;
  }

  const returns = emptyReturnSums();
  addLotReturns(returns, holding);
  grouped.set(holding.ticker, {
    ticker: holding.ticker,
    name: holding.name,
    units: holding.units,
    cost_basis_gbp: holding.cost_basis_gbp ?? 0,
    effective_cost_basis_gbp: holdingCost,
    market_value_gbp: holding.market_value_gbp ?? 0,
    gain_gbp: lotGain,
    gainCost: lotGainCost,
    hasKnownGain: gainKnown,
    returns,
    lot_count: 1,
    owners: [],
    accounts: [],
    acquired_date: null,
    days_held: null,
    sell_eligible: null,
    days_until_eligible: null,
    next_eligible_sell_date: null,
    current_price_gbp: holding.current_price_gbp ?? null,
    current_price_currency: holding.current_price_currency ?? null,
    currency: holding.currency ?? null,
    instrument_type: holding.instrument_type ?? null,
    ownerSet: new Set([holding.owner]),
    accountSet: new Set([holding.source_account]),
    oldestLot: holding,
  });
}

/**
 * Combine account lots into one portfolio-level position per ticker.
 *
 * `asOf` is the portfolio snapshot date (e.g. `portfolio.as_of`) used to
 * recompute days_held against the oldest lot's acquired_date, mirroring how
 * a single-account holding's days_held is derived. When omitted, the current
 * date is used.
 */
export function toRollupRows(
  holdings: ScopedHoldingRow[],
  instruments: InstrumentSummary[] = [],
  asOf?: string,
): RollupRow[] {
  const grouped = new Map<string, MutableRollup>();

  for (const holding of holdings) {
    addHolding(grouped, holding);
  }

  const snapshotTime = asOf ? Date.parse(asOf) : Date.now();

  const scopedTotal = Array.from(grouped.values()).reduce(
    (total, row) => total + row.market_value_gbp,
    0,
  );
  const instrumentByTicker = new Map(
    instruments.map((instrument) => [instrument.ticker, instrument]),
  );

  return Array.from(grouped.values(), (row) => {
    const instrument = instrumentByTicker.get(row.ticker);
    const {
      ownerSet,
      accountSet,
      oldestLot,
      gainCost,
      hasKnownGain,
      returns,
      ...rollup
    } = row;

    const acquiredDate = hasValidAcquiredDate(oldestLot)
      ? oldestLot.acquired_date!
      : null;
    const acquiredTime = acquiredDate ? Date.parse(acquiredDate) : Number.NaN;
    const rawDaysHeld =
      Number.isNaN(snapshotTime) || Number.isNaN(acquiredTime)
        ? (oldestLot.days_held ?? null)
        : Math.floor((snapshotTime - acquiredTime) / 86_400_000);
    // A negative value means `asOf` predates the acquisition date (e.g. a
    // historical snapshot requested before the holding existed) — that's not
    // a valid days-held count, so surface it as unavailable rather than
    // silently clamping to 0, which would look like "acquired today".
    const daysHeld = rawDaysHeld != null && rawDaysHeld < 0 ? null : rawDaysHeld;

    return {
      ...rollup,
      gain_gbp: hasKnownGain ? row.gain_gbp : null,
      gain_pct:
        hasKnownGain && gainCost > 0 ? (row.gain_gbp / gainCost) * 100 : null,
      cost_basis_source: hasKnownGain ? null : COST_BASIS_UNKNOWN,
      ...finishReturns(returns, row.market_value_gbp),
      weight_pct: scopedTotal
        ? (row.market_value_gbp / scopedTotal) * 100
        : 0,
      acquired_date: acquiredDate,
      days_held: daysHeld,
      sell_eligible: oldestLot.sell_eligible ?? null,
      days_until_eligible: oldestLot.days_until_eligible ?? null,
      next_eligible_sell_date: oldestLot.next_eligible_sell_date ?? null,
      owners: Array.from(ownerSet),
      accounts: Array.from(accountSet),
      grouping: instrument?.grouping ?? null,
      // `||` so a blank instrument sector still falls back to the lot's.
      sector: instrument?.sector?.trim() || oldestLot.sector?.trim() || null,
      exchange: instrument?.exchange ?? null,
      change_7d_pct: instrument?.change_7d_pct ?? null,
      change_30d_pct: instrument?.change_30d_pct ?? null,
    };
  });
}
