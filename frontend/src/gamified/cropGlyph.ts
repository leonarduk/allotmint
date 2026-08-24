/**
 * Deterministic produce icon for a holding.
 *
 * A crop must look the same every time it is rendered, so the glyph is a pure
 * function of ticker + sector: sector picks the pool (financials get the
 * orchard fruit, tech gets the glasshouse exotics), and a stable string hash
 * picks the entry within it.
 */

const SECTOR_POOLS: Record<string, readonly string[]> = {
  technology: ['🌶️', '🍆', '🥑', '🫑'],
  'information technology': ['🌶️', '🍆', '🥑', '🫑'],
  financials: ['🍎', '🍐', '🍏', '🍑'],
  'financial services': ['🍎', '🍐', '🍏', '🍑'],
  healthcare: ['🌿', '🍀', '☘️', '🌾'],
  energy: ['🌻', '🌽', '🎃', '🍄'],
  utilities: ['🥔', '🧅', '🧄', '🫚'],
  industrials: ['🥕', '🍠', '🌰', '🫛'],
  'consumer staples': ['🥬', '🥦', '🫘', '🥒'],
  'consumer discretionary': ['🍓', '🫐', '🍇', '🍒'],
  'real estate': ['🌳', '🌲', '🎋', '🌴'],
  materials: ['🪵', '🪴', '🌵', '🌱'],
  'communication services': ['🌼', '🌺', '🪻', '🌷'],
  cash: ['🪣', '💧', '🫙', '🧺'],
};

const DEFAULT_POOL: readonly string[] = [
  '🥬',
  '🥕',
  '🍅',
  '🥦',
  '🌽',
  '🫑',
  '🧅',
  '🥔',
];

/** FNV-1a — small, dependency-free, and stable across runs. */
export function hashString(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function cropGlyph(ticker: string, sector?: string | null): string {
  const pool =
    SECTOR_POOLS[(sector ?? '').trim().toLowerCase()] ?? DEFAULT_POOL;
  return pool[hashString(ticker || 'unknown') % pool.length];
}
