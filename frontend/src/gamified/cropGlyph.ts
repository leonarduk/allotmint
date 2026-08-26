/**
 * Deterministic crop species for a holding.
 *
 * A crop must look the same every time it is rendered, so the species is a
 * pure function of ticker + sector: sector picks the pool (financials get the
 * orchard fruit, energy gets the tall sun-lovers), and a stable string hash
 * picks the entry within it.
 *
 * The pools previously held emoji. They now hold names from the drawn glyph
 * set, which is the same structure with a different vocabulary — the sector
 * flavouring is deliberately preserved.
 *
 * Twelve shapes cannot uniquely identify a holding, and are not asked to: at
 * eight holdings the chance of a repeated species is about 95%. The species is
 * flavour, and the growth stage colours and fills it; the ticker printed
 * directly beneath is what identifies the crop.
 */

import type { CropSpecies } from './glyphShapes';

const SECTOR_POOLS: Record<string, readonly CropSpecies[]> = {
  technology: ['tomato', 'peapod', 'beanpod', 'strawberry'],
  'information technology': ['tomato', 'peapod', 'beanpod', 'strawberry'],
  financials: ['apple', 'pear', 'strawberry', 'tomato'],
  'financial services': ['apple', 'pear', 'strawberry', 'tomato'],
  healthcare: ['leek', 'peapod', 'corn', 'beanpod'],
  energy: ['sunflower', 'corn', 'pumpkin', 'beetroot'],
  utilities: ['beetroot', 'carrot', 'leek', 'pumpkin'],
  industrials: ['carrot', 'beetroot', 'peapod', 'corn'],
  'consumer staples': ['leek', 'beanpod', 'peapod', 'carrot'],
  'consumer discretionary': ['strawberry', 'tomato', 'peapod', 'apple'],
  'real estate': ['pumpkin', 'sunflower', 'corn', 'beetroot'],
  materials: ['beanpod', 'carrot', 'leek', 'sunflower'],
  'communication services': ['sunflower', 'strawberry', 'pear', 'tomato'],
  cash: ['beanpod', 'peapod', 'pumpkin', 'apple'],
};

const DEFAULT_POOL: readonly CropSpecies[] = [
  'leek',
  'carrot',
  'tomato',
  'beanpod',
  'corn',
  'peapod',
  'beetroot',
  'pumpkin',
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

export function cropSpecies(
  ticker: string,
  sector?: string | null
): CropSpecies {
  const pool =
    SECTOR_POOLS[(sector ?? '').trim().toLowerCase()] ?? DEFAULT_POOL;
  return pool[hashString(ticker || 'unknown') % pool.length];
}
