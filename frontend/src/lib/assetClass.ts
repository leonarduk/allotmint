// Mirrors backend/common/instrument_classification.py (#9196): asset classes
// are stored lower-case ("equity") since #9196, but metadata persisted before
// it (or a stale S3 copy) still says "Equity"/"Bond"/"Commodity". Every
// spelling of one asset class must group and render as the same label.
const ASSET_CLASS_ALIASES: Record<string, string> = {
  equity: 'equity',
  equities: 'equity',
  stock: 'equity',
  stocks: 'equity',
  share: 'equity',
  shares: 'equity',
  bond: 'bond',
  bonds: 'bond',
  'fixed income': 'bond',
  cash: 'cash',
  'money market': 'cash',
  moneymarket: 'cash',
  commodity: 'commodity',
  commodities: 'commodity',
  property: 'property',
  'real estate': 'property',
  'multi-asset': 'multi-asset',
  'multi asset': 'multi-asset',
  'mixed assets': 'multi-asset',
  allocation: 'multi-asset',
};

const ASSET_CLASS_LABELS: Record<string, string> = {
  equity: 'Equity',
  bond: 'Bond',
  cash: 'Cash',
  commodity: 'Commodity',
  property: 'Property',
  'multi-asset': 'Multi-asset',
};

/** Canonical asset class for ``value``, or ``null`` when unrecognised. */
export function normaliseAssetClass(value?: string | null): string | null {
  if (typeof value !== 'string') return null;
  return ASSET_CLASS_ALIASES[value.trim().toLowerCase()] ?? null;
}

/**
 * Display label for an asset class, case-insensitively: "Equity" and
 * "equity" both give "Equity". An unrecognised label is returned trimmed;
 * a missing one gives ``fallback``.
 */
export function assetClassLabel(
  value?: string | null,
  fallback = 'Unknown'
): string {
  const canonical = normaliseAssetClass(value);
  if (canonical) return ASSET_CLASS_LABELS[canonical];
  const trimmed = typeof value === 'string' ? value.trim() : '';
  return trimmed || fallback;
}

// Mirrors backend/common/sub_asset_class.py (#9543, #9653): Equity, Bond and
// Commodity can be targeted by sub-class on the strategy page. Keys match
// allotmint-pro's backtest_portfolio asset-class blocks, except broad_equity,
// which the backtest calls "equity" when it sits beside small_cap_value.
export const SUB_ASSET_CLASSES: Record<
  string,
  Array<{ key: string; label: string }>
> = {
  equity: [
    { key: 'broad_equity', label: 'Broad equity' },
    { key: 'small_cap_value', label: 'Small-cap value' },
  ],
  bond: [
    { key: 'long_gilts', label: 'Long gilts' },
    { key: 'intermediate_gilts', label: 'Intermediate gilts' },
    { key: 'short_gilts', label: 'Short gilts / ultrashort' },
    { key: 'index_linked', label: 'Index-linked' },
    { key: 'overseas_government', label: 'Overseas government' },
    { key: 'corporate_bonds', label: 'Corporate / credit' },
  ],
  commodity: [
    { key: 'gold', label: 'Gold' },
    { key: 'commodities', label: 'Other commodities' },
  ],
};

const SUB_ASSET_CLASS_LABELS: Record<string, string> = Object.fromEntries(
  Object.values(SUB_ASSET_CLASSES).flatMap((subs) =>
    subs.map(({ key, label }) => [key, label])
  )
);

/** Parent asset class of a sub-class key, or ``null`` for anything else. */
export function subAssetClassParent(key: string): string | null {
  for (const [parent, subs] of Object.entries(SUB_ASSET_CLASSES)) {
    if (subs.some((sub) => sub.key === key)) return parent;
  }
  return null;
}

/** Label for a rebalance target key: a sub-class or an asset class. */
export function allocationKeyLabel(key: string): string {
  return SUB_ASSET_CLASS_LABELS[key] ?? assetClassLabel(key, key);
}
