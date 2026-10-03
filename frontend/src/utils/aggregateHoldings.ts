import type { Holding } from "../types";
import { isCostBasisUnreliable } from "../lib/costBasis";

export type ScopedHolding = Holding & {
  source_account?: string;
  row_key: string;
};

const sum = (values: Array<number | null | undefined>): number =>
  values.reduce<number>((total, value) => total + (value ?? 0), 0);

/**
 * Combine account lots into one portfolio-level position per ticker.
 *
 * Dates and eligibility describe the oldest lot: its acquisition date is the
 * earliest date, days held is recalculated at the portfolio snapshot, and its
 * eligibility metadata is retained. Instrument metadata and prices come from
 * the first lot because they describe the ticker rather than an account lot.
 */
export const aggregateHoldingsByTicker = (
  holdings: ScopedHolding[],
  asOf: string,
): ScopedHolding[] => {
  const grouped = new Map<string, ScopedHolding[]>();
  holdings.forEach((holding) => {
    const lots = grouped.get(holding.ticker) ?? [];
    lots.push(holding);
    grouped.set(holding.ticker, lots);
  });

  return Array.from(grouped, ([ticker, lots]) => {
    const first = lots[0];
    const datedLots = lots
      .filter(
        (lot) =>
          lot.acquired_date && !Number.isNaN(Date.parse(lot.acquired_date)),
      )
      .sort(
        (left, right) =>
          Date.parse(left.acquired_date!) - Date.parse(right.acquired_date!),
      );
    const oldest = datedLots[0] ?? first;
    const acquiredDate = oldest.acquired_date ?? null;
    const snapshotTime = Date.parse(asOf);
    const acquiredTime = acquiredDate ? Date.parse(acquiredDate) : Number.NaN;
    const daysHeld =
      Number.isNaN(snapshotTime) || Number.isNaN(acquiredTime)
        ? oldest.days_held
        : Math.max(0, Math.floor((snapshotTime - acquiredTime) / 86_400_000));
    const lotCost = (lot: ScopedHolding): number =>
      ((lot.cost_basis_gbp ?? 0) > 0
        ? lot.cost_basis_gbp
        : lot.effective_cost_basis_gbp) ?? 0;
    const costBasis = sum(lots.map(lotCost));
    // Only lots with a real cost carry a gain (#8471): a zero cost or the
    // last-resort guessed cost (#7220) must not count as break-even.
    const gainLots = lots.filter(
      (lot) =>
        lot.gain_gbp != null &&
        !isCostBasisUnreliable(lot.cost_basis_source) &&
        lotCost(lot) > 0,
    );
    const gain = gainLots.length
      ? sum(gainLots.map((lot) => lot.gain_gbp))
      : null;
    const gainCost = sum(gainLots.map(lotCost));

    return {
      ...first,
      ticker,
      units: sum(lots.map((lot) => lot.units)),
      market_value_gbp: sum(lots.map((lot) => lot.market_value_gbp)),
      cost_basis_gbp: costBasis,
      effective_cost_basis_gbp: costBasis,
      gain_gbp: gain,
      gain_pct: gain !== null && gainCost > 0 ? (gain / gainCost) * 100 : null,
      cost_basis_source: gainLots.length
        ? gainLots[0].cost_basis_source
        : first.cost_basis_source,
      day_change_gbp: sum(lots.map((lot) => lot.day_change_gbp)),
      acquired_date: acquiredDate,
      days_held: daysHeld,
      sell_eligible: oldest.sell_eligible,
      days_until_eligible: oldest.days_until_eligible,
      next_eligible_sell_date: oldest.next_eligible_sell_date,
      source_account: undefined,
      row_key: `all-${ticker}`,
    };
  });
};
