import type { InstrumentSummary } from '@/types';

export type RowWithCost = InstrumentSummary & {
  cost: number;
  gain_pct: number;
};

export type GroupTotals = {
  labelValue: string;
  units: number;
  cost: number;
  marketValue: number;
  gain: number;
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

export type GroupingMode = 'group' | 'flat' | 'category';

export type VisibleColumns = {
  units: boolean;
  cost: boolean;
  market: boolean;
  gain: boolean;
  gain_pct: boolean;
};
