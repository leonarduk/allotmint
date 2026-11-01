import type { Account } from '../types';
import { isCostBasisUnreliable } from './costBasis';

/** A holding whose gain is excluded because its cost basis is unreliable (#7825). */
export type CostBasisGap = {
  owner: string;
  account: string;
  ticker: string;
  name: string;
  units: number;
  /** Market value in GBP, or null when the holding has no price. */
  marketValue: number | null;
  /** The cost_basis_source that made it unreliable ("unknown" or "book_suspect"). */
  source: string;
};

/**
 * Holdings with an unreliable cost basis, largest market value first, so the
 * first few entries recover most of the portfolio by value. Unpriced holdings
 * sort last. Uses the same test as the dashboard's gain exclusion
 * (computePortfolioTotals), so the list length matches its "Excludes N" count.
 */
export function buildCostBasisChecklist(accounts: Account[]): CostBasisGap[] {
  const gaps: CostBasisGap[] = [];
  for (const acct of accounts) {
    for (const h of acct.holdings ?? []) {
      if (!isCostBasisUnreliable(h.cost_basis_source)) continue;
      gaps.push({
        owner: acct.owner ?? '',
        account: acct.account_type,
        ticker: h.ticker,
        name: h.name || h.ticker,
        units: h.units,
        marketValue: h.market_value_gbp ?? null,
        source: h.cost_basis_source as string,
      });
    }
  }
  return gaps.sort((a, b) => {
    if (a.marketValue === null && b.marketValue === null) return 0;
    if (a.marketValue === null) return 1;
    if (b.marketValue === null) return -1;
    return b.marketValue - a.marketValue;
  });
}

/** Share (0-1) of the gaps' total market value held by the first ``count`` gaps. */
export function topValueShare(gaps: CostBasisGap[], count: number): number {
  const total = gaps.reduce((sum, g) => sum + (g.marketValue ?? 0), 0);
  if (total <= 0) return 0;
  const top = gaps
    .slice(0, count)
    .reduce((sum, g) => sum + (g.marketValue ?? 0), 0);
  return top / total;
}

/** Columns of the purchase-price CSV that POST /holdings/cost-basis/import reads (#10095). */
export const COST_BASIS_CSV_HEADERS = [
  'owner',
  'account',
  'ticker',
  'date',
  'units',
  'unit_cost',
] as const;

const csvCell = (value: string | number): string => {
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

/**
 * A purchase-price CSV with one row per gap, owner/account/ticker/units filled
 * and date/unit_cost left blank for the user to complete. A holding bought in
 * several lots can be split into several rows whose units add up to the total.
 */
export function buildCostBasisTemplateCsv(gaps: CostBasisGap[]): string {
  const rows = gaps.map((g) =>
    [g.owner, g.account, g.ticker, '', g.units, ''].map(csvCell).join(',')
  );
  return `${[COST_BASIS_CSV_HEADERS.join(','), ...rows].join('\r\n')}\r\n`;
}

/** The one owner every gap belongs to, else undefined (the CSV's owner column decides). */
export function singleGapOwner(gaps: CostBasisGap[]): string | undefined {
  const owners = new Set(gaps.map((g) => g.owner).filter(Boolean));
  return owners.size === 1 ? [...owners][0] : undefined;
}

/**
 * Link to the set-holding form on /input, prefilled for this holding. Saving
 * there with a unit price records a priced transfer-in, which the holdings
 * rebuild books as the holding's cost (backend/common/holdings_rebuild.py).
 */
export function costBasisFillHref(gap: CostBasisGap): string {
  const params = new URLSearchParams({
    owner: gap.owner,
    account: gap.account,
    ticker: gap.ticker,
    units: String(gap.units),
  });
  return `/input?${params.toString()}`;
}
