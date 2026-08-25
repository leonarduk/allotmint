import { describe, expect, it } from 'vitest';
import { cropSpecies, hashString } from '@/gamified/cropGlyph';
import { CROP_SPECIES, GLYPH_SHAPES, STAGE_FILL } from '@/gamified/glyphShapes';
import { GROWTH_STAGES } from '@/gamified/plotModel';

describe('cropSpecies', () => {
  it('is stable for the same ticker and sector', () => {
    const first = cropSpecies('VUSA.L', 'Financials');
    const second = cropSpecies('VUSA.L', 'Financials');
    expect(first).toBe(second);
  });

  it('draws from the sector pool when one is defined', () => {
    const orchard = ['apple', 'pear', 'strawberry', 'tomato'];
    expect(orchard).toContain(cropSpecies('HSBA.L', 'Financials'));
    expect(orchard).toContain(cropSpecies('LLOY.L', 'financial services'));
  });

  it('falls back to the default pool for unknown or missing sectors', () => {
    const fallback = [
      'leek',
      'carrot',
      'tomato',
      'beanpod',
      'corn',
      'peapod',
      'beetroot',
      'pumpkin',
    ];
    expect(fallback).toContain(cropSpecies('ABC.L', 'Something Unmapped'));
    expect(fallback).toContain(cropSpecies('ABC.L', null));
    expect(fallback).toContain(cropSpecies('', undefined));
  });

  it('only ever names a species the glyph set can draw', () => {
    const sectors = [
      'Financials',
      'Technology',
      'Energy',
      'Utilities',
      'Cash',
      'Nonsense',
      null,
    ];
    for (const sector of sectors) {
      for (const ticker of ['A', 'BP.L', 'VWRL.L', 'SMT.L', '']) {
        expect(CROP_SPECIES).toContain(cropSpecies(ticker, sector));
      }
    }
  });

  it('hashes deterministically and stays a 32-bit unsigned integer', () => {
    expect(hashString('VUSA.L')).toBe(hashString('VUSA.L'));
    expect(hashString('VUSA.L')).not.toBe(hashString('WILT.L'));
    expect(hashString('anything')).toBeGreaterThanOrEqual(0);
    expect(hashString('anything')).toBeLessThan(2 ** 32);
  });
});

describe('glyph shapes', () => {
  it('has a drawable shape for every named species', () => {
    for (const species of CROP_SPECIES) {
      expect(GLYPH_SHAPES[species].body).toMatch(/^M[\d.\s]/);
      expect(GLYPH_SHAPES[species].body.trimEnd().endsWith('Z')).toBe(true);
    }
  });

  it('covers every growth stage with a fill fraction', () => {
    for (const stage of GROWTH_STAGES) {
      const fill = STAGE_FILL[stage.id];
      expect(fill).toBeGreaterThan(0);
      expect(fill).toBeLessThanOrEqual(1);
    }
  });

  it('fills more of the silhouette the further a crop has grown', () => {
    const ladder = GROWTH_STAGES.map((stage) => STAGE_FILL[stage.id]);
    const ascending = [...ladder].sort((a, b) => a - b);
    expect(ladder).toEqual(ascending);
    expect(new Set(ladder).size).toBe(ladder.length);
  });

  it('never leaves a wilting crop as an empty outline', () => {
    // An empty shape reads as "no data", which is a different and more
    // alarming claim than "down 20%".
    expect(STAGE_FILL.wilting).toBeGreaterThan(0);
    expect(STAGE_FILL.bumper).toBe(1);
  });
});
