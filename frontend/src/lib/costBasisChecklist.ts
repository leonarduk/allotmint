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
