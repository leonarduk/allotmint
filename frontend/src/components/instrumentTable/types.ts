import type { InstrumentSummary } from '@/types';

export type RowWithCost = InstrumentSummary & {
  cost: number;
  gain_pct: number;
};

export type GroupTotals = {
  labelValue: string;
  units: number;
  /** Distinct tickers in the group; summed units are only meaningful when this is 1 (#8531). */
  instrumentCount: number;
  /** Null when no row in the group has a reliable cost basis (#8531). */
  cost: number | null;
  marketValue: number;
  /** Null when no row in the group has a reliable cost basis (#8531). */
  gain: number | null;
  gainPct: number | null;
  change7dPct: number | null;
  change30dPct: number | null;
};

export type GroupedRows = {
  key: string;
  label: string;
  rows: RowWithCost[];
  totals: GroupTotals;
};

export type GroupingMode = 'group' | 'flat' | 'category' | 'sector';

export type VisibleColumns = {
  units: boolean;
  cost: boolean;
  market: boolean;
  gain: boolean;
  gain_pct: boolean;
  trend: boolean;
};
