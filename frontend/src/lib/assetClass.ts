import i18n from '../i18n';

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

/** Translated display label for a canonical class or sub-class key. */
export const classKeyLabel = (key: string): string =>
  i18n.t(`assetClasses.${key}`);

/** A ``{ key, label }`` option whose label is translated when read. */
const option = (key: string): { key: string; label: string } => ({
  key,
  get label() {
    return classKeyLabel(key);
  },
});

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
  fallback = i18n.t('assetClasses.unknown')
): string {
  const canonical = normaliseAssetClass(value);
  if (canonical) return classKeyLabel(canonical);
  const trimmed = typeof value === 'string' ? value.trim() : '';
  return trimmed || fallback;
}

// Mirrors backend/common/sub_asset_class.py (#9543, #9653): Equity, Bond and
// Commodity can be targeted by sub-class on the strategy page. Keys match
// allotmint-pro's backtest_portfolio asset-class blocks, except broad_equity,
// which the backtest calls "equity" when it sits beside small_cap_value.
export { option as assetClassOption };

export const SUB_ASSET_CLASSES: Record<
  string,
  Array<{ key: string; label: string }>
> = {
  equity: [option('broad_equity'), option('small_cap_value')],
  bond: [
    option('long_gilts'),
    option('intermediate_gilts'),
    option('short_gilts'),
    option('index_linked'),
    option('overseas_government'),
    option('corporate_bonds'),
  ],
  commodity: [option('gold'), option('commodities')],
};

/** Parent asset class of a sub-class key, or ``null`` for anything else. */
export function subAssetClassParent(key: string): string | null {
  for (const [parent, subs] of Object.entries(SUB_ASSET_CLASSES)) {
    if (subs.some((sub) => sub.key === key)) return parent;
  }
  return null;
}

/** Label for a rebalance target key: a sub-class or an asset class. */
export function allocationKeyLabel(key: string): string {
  return subAssetClassParent(key)
    ? classKeyLabel(key)
    : assetClassLabel(key, key);
}
