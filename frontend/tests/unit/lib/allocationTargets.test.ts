import { describe, expect, it } from 'vitest';
import {
  activeKeys,
  currentWeights,
  draftFromCurrent,
  draftFromTargets,
  draftTotal,
  targetsFromDraft,
  toggleSplit,
} from '@/lib/allocationTargets';
import { allocationKeyLabel, subAssetClassParent } from '@/lib/assetClass';
import type { RebalancePlan } from '@/types';

// Sub-class rebalance targets (#9543): a class is targeted as a whole or by
// sub-class, never both.

const USER_TARGETS = {
  equity: 40,
  long_gilts: 10,
  intermediate_gilts: 10,
  short_gilts: 20,
  gold: 20,
};

describe('draftFromTargets', () => {
  it('keeps a class-level policy unsplit', () => {
    const draft = draftFromTargets({ equity: 60, bond: 40 });
    expect(draft.split).toEqual([]);
    expect(draft.values.bond).toBe('40');
    expect(targetsFromDraft(draft)).toEqual({ equity: 60, bond: 40 });
  });

  it('splits a class whose sub-classes have targets', () => {
    const draft = draftFromTargets(USER_TARGETS);
    expect(draft.split).toEqual(['bond', 'commodity']);
    expect(draftTotal(draft)).toBe(100);
    expect(targetsFromDraft(draft)).toEqual(USER_TARGETS);
  });
});

describe('activeKeys', () => {
  it('replaces a split class with its sub-classes in display order', () => {
    expect(activeKeys(['commodity'])).toEqual([
      'equity',
      'bond',
      'cash',
      'gold',
      'other_commodities',
      'property',
      'multi-asset',
    ]);
  });
});

describe('toggleSplit', () => {
  it('only counts the active level towards the total and saved targets', () => {
    const split = toggleSplit(
      draftFromTargets({ equity: 60, bond: 40 }),
      'bond'
    );
    // Bond's own 40 no longer counts until sub-classes are filled in.
    expect(draftTotal(split)).toBe(60);
    const filled = {
      ...split,
      values: { ...split.values, long_gilts: '15', short_gilts: '25' },
    };
    expect(draftTotal(filled)).toBe(100);
    expect(targetsFromDraft(filled)).toEqual({
      equity: 60,
      long_gilts: 15,
      short_gilts: 25,
    });
  });

  it('carries the sub-class total back to the class when combining', () => {
    const combined = toggleSplit(draftFromTargets(USER_TARGETS), 'bond');
    expect(combined.split).toEqual(['commodity']);
    expect(combined.values.bond).toBe('40');
    expect(targetsFromDraft(combined)).toEqual({
      equity: 40,
      bond: 40,
      gold: 20,
    });
  });

  it('keeps the class value when combining with no sub-class input', () => {
    const draft = toggleSplit(draftFromTargets({ bond: 100 }), 'bond');
    expect(toggleSplit(draft, 'bond').values.bond).toBe('100');
  });
});

function plan(overrides: Partial<RebalancePlan>): RebalancePlan {
  return {
    policy: { targets: {}, tolerance_pct: 5 },
    total_value: 1000,
    classes: [],
    unclassified_value: 0,
    unclassified_pct: 0,
    unpriced_tickers: [],
    accounts: [],
    trades: [],
    unfunded_amount: 0,
    notes: [],
    ...overrides,
  };
}

const row = (asset_class: string, current_pct: number, parent?: string) => ({
  asset_class,
  parent: parent ?? null,
  label: asset_class,
  current_value: current_pct * 10,
  current_pct,
  target_pct: null,
  drift_pct: null,
  in_band: null,
});

describe('currentWeights', () => {
  it('reports class and sub-class weights, summing split classes', () => {
    const weights = currentWeights(
      plan({
        classes: [
          row('equity', 60),
          row('long_gilts', 10, 'bond'),
          row('bond', 5, 'bond'),
        ],
        sub_classes: [
          { ...row('long_gilts', 10, 'bond'), parent: 'bond' },
          { ...row('bond', 5, 'bond'), parent: 'bond' },
          { ...row('gold', 25, 'commodity'), parent: 'commodity' },
        ],
      })
    );
    expect(weights).toEqual({
      equity: 60,
      bond: 15,
      long_gilts: 10,
      commodity: 25,
      gold: 25,
    });
  });

  it('fills sub-class inputs from the current allocation', () => {
    const draft = draftFromCurrent(
      plan({
        classes: [row('equity', 70), row('bond', 30)],
        sub_classes: [
          { ...row('long_gilts', 10, 'bond'), parent: 'bond' },
          { ...row('short_gilts', 20, 'bond'), parent: 'bond' },
        ],
      }),
      ['bond']
    );
    expect(draftTotal(draft)).toBe(100);
    expect(draft.values.bond).toBe('30');
  });
});

describe('sub-class labels', () => {
  it('labels sub-class and class keys and maps sub-classes to parents', () => {
    expect(allocationKeyLabel('short_gilts')).toBe('Short gilts / ultrashort');
    expect(allocationKeyLabel('bond')).toBe('Bond');
    expect(subAssetClassParent('gold')).toBe('commodity');
    expect(subAssetClassParent('equity')).toBeNull();
  });
});
