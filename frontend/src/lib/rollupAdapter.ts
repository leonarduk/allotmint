import type { Account, Holding, InstrumentSummary } from "../types";

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
  gain_gbp: number;
  gain_pct: number;
  weight_pct: number;
  lot_count: number;
  owners: string[];
  accounts: string[];
  grouping: string | null;
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
};

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
  | "exchange"
  | "change_7d_pct"
  | "change_30d_pct"
> & {
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

  const existing = grouped.get(holding.ticker);
  if (existing) {
    existing.units += holding.units;
    existing.cost_basis_gbp += holding.cost_basis_gbp ?? 0;
    existing.effective_cost_basis_gbp += holdingCost;
    existing.market_value_gbp += holding.market_value_gbp ?? 0;
    existing.gain_gbp += holding.gain_gbp ?? 0;
    existing.lot_count += 1;
    existing.ownerSet.add(holding.owner);
    existing.accountSet.add(holding.source_account);
    if (isEarlierAcquisition(holding, existing.oldestLot)) {
      existing.oldestLot = holding;
    }
    return;
  }

  grouped.set(holding.ticker, {
    ticker: holding.ticker,
    name: holding.name,
    units: holding.units,
    cost_basis_gbp: holding.cost_basis_gbp ?? 0,
    effective_cost_basis_gbp: holdingCost,
    market_value_gbp: holding.market_value_gbp ?? 0,
    gain_gbp: holding.gain_gbp ?? 0,
    gain_pct: 0,
    lot_count: 1,
    owners: [],
    accounts: [],
    acquired_date: null,
    days_held: null,
    sell_eligible: null,
    days_until_eligible: null,
    next_eligible_sell_date: null,
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
    const { ownerSet, accountSet, oldestLot, ...rollup } = row;

    const acquiredDate = hasValidAcquiredDate(oldestLot)
      ? oldestLot.acquired_date!
      : null;
    const acquiredTime = acquiredDate ? Date.parse(acquiredDate) : Number.NaN;
    const daysHeld =
      Number.isNaN(snapshotTime) || Number.isNaN(acquiredTime)
        ? (oldestLot.days_held ?? null)
        : Math.max(0, Math.floor((snapshotTime - acquiredTime) / 86_400_000));

    return {
      ...rollup,
      gain_pct: row.effective_cost_basis_gbp
        ? (row.gain_gbp / row.effective_cost_basis_gbp) * 100
        : 0,
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
      exchange: instrument?.exchange ?? null,
      change_7d_pct: instrument?.change_7d_pct ?? null,
      change_30d_pct: instrument?.change_30d_pct ?? null,
    };
  });
}
