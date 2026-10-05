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
