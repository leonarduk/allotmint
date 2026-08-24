import { describe, expect, it } from 'vitest';
import { cropGlyph, hashString } from '@/gamified/cropGlyph';

describe('cropGlyph', () => {
  it('is stable for the same ticker and sector', () => {
    const first = cropGlyph('VUSA.L', 'Financials');
    const second = cropGlyph('VUSA.L', 'Financials');
    expect(first).toBe(second);
  });

  it('draws from the sector pool when one is defined', () => {
    const orchard = ['🍎', '🍐', '🍏', '🍑'];
    expect(orchard).toContain(cropGlyph('HSBA.L', 'Financials'));
    expect(orchard).toContain(cropGlyph('LLOY.L', 'financial services'));
  });

  it('falls back to the default pool for unknown or missing sectors', () => {
    const fallback = ['🥬', '🥕', '🍅', '🥦', '🌽', '🫑', '🧅', '🥔'];
    expect(fallback).toContain(cropGlyph('ABC.L', 'Something Unmapped'));
    expect(fallback).toContain(cropGlyph('ABC.L', null));
    expect(fallback).toContain(cropGlyph('', undefined));
  });

  it('hashes deterministically and stays a 32-bit unsigned integer', () => {
    expect(hashString('VUSA.L')).toBe(hashString('VUSA.L'));
    expect(hashString('VUSA.L')).not.toBe(hashString('WILT.L'));
    expect(hashString('anything')).toBeGreaterThanOrEqual(0);
    expect(hashString('anything')).toBeLessThan(2 ** 32);
  });
});
