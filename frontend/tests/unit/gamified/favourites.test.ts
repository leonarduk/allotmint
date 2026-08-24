import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  loadFavourites,
  matchesSearch,
  saveFavourites,
  toggleFavourite,
} from '@/gamified/favourites';

describe('favourites storage', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('round-trips a set, namespaced per grower', () => {
    saveFavourites('steve', new Set(['VUSA.L', 'SMT.L']));
    expect([...loadFavourites('steve')].sort()).toEqual(['SMT.L', 'VUSA.L']);
    // A different grower on the same device sees their own (empty) marks.
    expect([...loadFavourites('alex')]).toEqual([]);
  });

  it('returns an empty set for missing, malformed or non-string entries', () => {
    expect([...loadFavourites('nobody')]).toEqual([]);

    window.localStorage.setItem('allotmint:plot:favourites:steve', 'not json');
    expect([...loadFavourites('steve')]).toEqual([]);

    window.localStorage.setItem(
      'allotmint:plot:favourites:steve',
      JSON.stringify({ nope: true })
    );
    expect([...loadFavourites('steve')]).toEqual([]);

    window.localStorage.setItem(
      'allotmint:plot:favourites:steve',
      JSON.stringify(['OK.L', 42, null])
    );
    expect([...loadFavourites('steve')]).toEqual(['OK.L']);
  });

  it('survives a localStorage that throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect([...loadFavourites('steve')]).toEqual([]);

    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => saveFavourites('steve', new Set(['A.L']))).not.toThrow();
  });
});

describe('toggleFavourite', () => {
  it('adds, removes, and never mutates the input set', () => {
    const original = new Set(['A.L']);
    const added = toggleFavourite(original, 'B.L');
    expect([...original]).toEqual(['A.L']);
    expect([...added].sort()).toEqual(['A.L', 'B.L']);
    expect([...toggleFavourite(added, 'A.L')]).toEqual(['B.L']);
  });
});

describe('matchesSearch', () => {
  const fields = ['VUSA.L', 'Vanguard S&P 500', 'Stocks Isa', 'Financials'];

  it('matches case-insensitively across every field', () => {
    expect(matchesSearch(fields, 'vusa')).toBe(true);
    expect(matchesSearch(fields, 'VANGUARD')).toBe(true);
    expect(matchesSearch(fields, 'isa')).toBe(true);
    expect(matchesSearch(fields, 'financ')).toBe(true);
    expect(matchesSearch(fields, 'gilt')).toBe(false);
  });

  it('treats an empty or whitespace query as "match everything"', () => {
    expect(matchesSearch(fields, '')).toBe(true);
    expect(matchesSearch(fields, '   ')).toBe(true);
    expect(matchesSearch([], '')).toBe(true);
  });
});
