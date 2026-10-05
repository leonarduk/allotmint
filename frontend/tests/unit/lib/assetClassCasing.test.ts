import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import { buildAllocationHierarchy } from '@/components/AllocationCharts';
import { assetClassLabel, normaliseAssetClass } from '@/lib/assetClass';
import { translateInstrumentType } from '@/lib/instrumentType';

// Asset classes are stored lower-case since #9196; metadata persisted before
// it still says "Equity"/"Bond". Both spellings must render and group alike.

const t = ((key: string, opts?: { defaultValue?: string }) =>
  `t:${key}${opts?.defaultValue ? `|${opts.defaultValue}` : ''}`) as unknown as TFunction;

describe('normaliseAssetClass', () => {
  it.each([
    ['Equity', 'equity'],
    ['equity', 'equity'],
    [' BOND ', 'bond'],
    ['Commodity', 'commodity'],
    ['Real Estate', 'property'],
    ['Fund', null],
    [null, null],
  ])('maps %s to %s', (value, expected) => {
    expect(normaliseAssetClass(value)).toBe(expected);
  });
});

describe('assetClassLabel', () => {
  it('labels legacy and canonical casing identically', () => {
    expect(assetClassLabel('Equity')).toBe('Equity');
    expect(assetClassLabel('equity')).toBe('Equity');
    expect(assetClassLabel('multi-asset')).toBe('Multi-asset');
  });

  it('keeps unknown labels and falls back when missing', () => {
    expect(assetClassLabel(' Fund ')).toBe('Fund');
    expect(assetClassLabel(null)).toBe('Unknown');
    expect(assetClassLabel('', 'Other')).toBe('Other');
  });
});

describe('translateInstrumentType', () => {
  it.each([
    ['Equity', 'instrumentType.equity'],
    ['equity', 'instrumentType.equity'],
    ['Bond', 'instrumentType.bond'],
    ['bond', 'instrumentType.bond'],
    ['Commodity', 'instrumentType.commodity'],
    ['commodity', 'instrumentType.commodity'],
    ['multi-asset', 'instrumentType.multiAsset'],
    ['property', 'instrumentType.realEstate'],
  ])('translates %s via %s', (type, key) => {
    expect(translateInstrumentType(t, type)).toBe(`t:${key}|${type}`);
  });

  it('returns an unmapped type unchanged', () => {
    expect(translateInstrumentType(t, 'MUTUALFUND')).toBe('MUTUALFUND');
  });
});

describe('buildAllocationHierarchy', () => {
  it('merges legacy and canonical asset-class casing into one node', () => {
    const tree = buildAllocationHierarchy([
      {
        ticker: 'A.L',
        market_value_gbp: 100,
        asset_class: 'Equity',
        industry: 'X',
        region: 'UK',
      },
      {
        ticker: 'B.L',
        market_value_gbp: 50,
        asset_class: 'equity',
        industry: 'X',
        region: 'UK',
      },
      {
        ticker: 'C.L',
        market_value_gbp: 25,
        asset_class: 'bond',
        industry: 'Y',
        region: 'UK',
      },
    ]);

    expect(tree.map((node) => node.name)).toEqual(['Equity', 'Bond']);
    const equity = tree[0];
    expect(equity.children?.[0].children?.[0]).toEqual({
      name: 'UK',
      value: 150,
    });
  });
});
