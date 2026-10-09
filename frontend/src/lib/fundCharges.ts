import type { Account, AllInCost, AllInCostPart } from '../types';
import { isCashInstrument } from './instruments';

/**
 * Portfolio-level fund charges (#7834).
 *
 * Only priced, non-cash holdings count. A holding whose `ongoing_charge_pct`
 * is null/absent is "unknown": it is left out of the weighted average and the
 * annual cost and counted separately, so missing fee data is never read as 0%.
 */
export type FundChargeTotals = {
  /** Value-weighted ongoing charge (%) over holdings with a known charge; null when none is known. */
  weightedChargePct: number | null;
  /** Estimated annual cost in GBP for holdings with a known charge; null when none is known. */
  annualCostGbp: number | null;
  /** Priced non-cash holdings considered. */
  holdingCount: number;
  /** Of those, holdings with no fee data. */
  unknownCount: number;
};

// Mirrors backend/common/fund_charges.py: a larger value is a data-entry slip
// (e.g. 22 typed for 0.22%) and is treated as unknown, as are negatives.
const MAX_PLAUSIBLE_CHARGE_PCT = 10;

function isKnownCharge(charge: number | null | undefined): charge is number {
  return (
    typeof charge === 'number' &&
    Number.isFinite(charge) &&
    charge >= 0 &&
    charge <= MAX_PLAUSIBLE_CHARGE_PCT
  );
}

export function computeFundCharges(accounts: Account[]): FundChargeTotals {
  let knownValue = 0;
  let annualCost = 0;
  let holdingCount = 0;
  let unknownCount = 0;

  for (const acct of accounts) {
    for (const h of acct.holdings ?? []) {
      const market = h.market_value_gbp;
      if (typeof market !== 'number' || !Number.isFinite(market) || market <= 0)
        continue;
      if (
        isCashInstrument({
          instrument_type: h.instrument_type,
          ticker: h.ticker,
        })
      )
        continue;
      holdingCount += 1;
      const charge = h.ongoing_charge_pct;
      if (!isKnownCharge(charge)) {
        unknownCount += 1;
        continue;
      }
      knownValue += market;
      annualCost += (market * charge) / 100;
    }
  }

  // Every known-charge holding has a positive market value (see the guard
  // above), so knownValue > 0 exactly when any charge is known; both figures
  // are therefore either both set or both unknown.
  const anyKnown = knownValue > 0;
  return {
    weightedChargePct: anyKnown ? (annualCost / knownValue) * 100 : null,
    annualCostGbp: anyKnown ? annualCost : null,
    holdingCount,
    unknownCount,
  };
}


function isAllInPart(value: unknown): value is AllInCostPart {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as AllInCostPart).known_cost_gbp === 'number'
  );
}

/**
 * The all-in cost row for the current scope (#10482): one account when an
 * account filter is active, else the total with its per-account rows.
 * Anything not shaped like the endpoint's response yields nothing to show.
 */
export function selectAllInCost(
  data: AllInCost | null | undefined,
  owner: string | null,
  accountType: string | null,
): { part: AllInCostPart | null; accounts: AllInCostPart[] } {
  if (!data || !isAllInPart(data.total) || !Array.isArray(data.accounts)) {
    return { part: null, accounts: [] };
  }
  const accounts = data.accounts.filter(isAllInPart);
  if (!accountType) return { part: data.total, accounts };
  const wanted = accountType.toLowerCase();
  const match = accounts.find(
    (row) =>
      (row.account ?? '').toLowerCase() === wanted &&
      (!owner || !row.owner || row.owner.toLowerCase() === owner.toLowerCase()),
  );
  return { part: match ?? null, accounts: [] };
}
