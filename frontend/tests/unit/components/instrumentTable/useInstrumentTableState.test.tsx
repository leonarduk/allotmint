import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { InstrumentGroupDefinition, InstrumentSummary } from '@/types';
import { useInstrumentTableState } from '@/components/instrumentTable/useInstrumentTableState';

const rows: InstrumentSummary[] = [
  {
    ticker: 'AAA',
    name: 'Alpha',
    grouping: 'Dividend Growth',
    exchange: 'L',
    currency: 'GBP',
    units: 10,
    market_value_gbp: 1000,
    gain_gbp: 100,
  },
  {
    ticker: 'BBB',
    name: 'Beta',
    grouping: 'Global Tech',
    exchange: 'N',
    currency: 'USD',
    units: 5,
    market_value_gbp: 500,
    gain_gbp: -50,
  },
];

const definitions: InstrumentGroupDefinition[] = [
  { id: 'income', name: 'Dividend Growth', category: 'income' },
];

describe('useInstrumentTableState', () => {
  it('derives exchanges, group options, and filters rows', () => {
    const { result } = renderHook(() => useInstrumentTableState(rows, definitions));

    expect(result.current.exchanges).toEqual(['L', 'N']);
    expect(result.current.groupOptions).toEqual(['Dividend Growth', 'Global Tech']);
    expect(result.current.hasCategories).toBe(true);

    act(() => {
      result.current.toggleExchangeSelection('L');
    });

    expect(result.current.selectedExchanges).toEqual(['N']);
    expect(result.current.rowsWithCost.map((row) => row.ticker)).toEqual(['BBB']);
  });

  it('falls back from category mode when categories disappear', () => {
    const { result, rerender } = renderHook(
      ({ activeDefinitions }) => useInstrumentTableState(rows, activeDefinitions),
      { initialProps: { activeDefinitions: definitions } },
    );

    act(() => {
      result.current.setGroupingMode('category');
    });
    expect(result.current.groupingMode).toBe('category');

    rerender({ activeDefinitions: [] });
    expect(result.current.groupingMode).toBe('group');
  });
});
