import type { ReactNode } from 'react';
import { money, percent } from '@/lib/money';
import { isCashInstrument } from '@/lib/instruments';
import i18n from '@/i18n';
import statusStyles from '@/styles/status.module.css';
import type { InstrumentGroupDefinition, InstrumentSummary } from '@/types';
import type { GroupedRows, GroupingMode, GroupTotals, RowWithCost } from './types';

const UNGROUPED_KEY = '__ungrouped__';

const GROUP_SUMMARY_SORT_MAP: Partial<Record<keyof RowWithCost, keyof GroupTotals>> = {
  ticker: 'labelValue',
  name: 'labelValue',
  currency: 'labelValue',
  instrument_type: 'labelValue',
  units: 'units',
  cost: 'cost',
  market_value_gbp: 'marketValue',
  gain_gbp: 'gain',
  change_7d_pct: 'change7dPct',
  change_30d_pct: 'change30dPct',
  gain_pct: 'gainPct',
};

export function collectExchanges(rows: InstrumentSummary[]): string[] {
  const values = new Set<string>();
  for (const row of rows) {
    const exchange = row.exchange?.trim();
    if (exchange) {
      values.add(exchange);
    }
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b));
}

export function filterRowsByExchange(
  rows: InstrumentSummary[],
  exchanges: string[],
  selectedExchanges: string[],
): InstrumentSummary[] {
  if (!rows.length) return [];
  if (!exchanges.length) return rows;
  if (!selectedExchanges.length) return [];
  const selectedSet = new Set(selectedExchanges);
  return rows.filter((row) => {
    const exchange = row.exchange?.trim();
    if (!exchange) return true;
    return selectedSet.has(exchange);
  });
}

export function createRowsWithCost(rows: InstrumentSummary[]): RowWithCost[] {
  return rows.map((row) => {
    const cost = row.market_value_gbp - row.gain_gbp;
    const gain_pct =
      row.gain_pct !== undefined && row.gain_pct !== null
        ? row.gain_pct
        : cost
          ? (row.gain_gbp / cost) * 100
          : 0;
    return { ...row, cost, gain_pct };
  });
}

export function buildCategoryLookup(groupDefinitions: InstrumentGroupDefinition[]) {
  const byGroup = new Map<string, { key: string; label: string }>();
  const categories = new Map<string, string>();

  for (const definition of groupDefinitions) {
    const rawCategory = typeof definition.category === 'string' ? definition.category.trim() : '';
    if (!rawCategory) continue;

    const categoryKey = rawCategory.toLocaleLowerCase();
    const categoryLabel =
      typeof definition.category_name === 'string' && definition.category_name.trim()
        ? definition.category_name.trim()
        : formatCategoryLabel(rawCategory);
    if (!categories.has(categoryKey)) {
      categories.set(categoryKey, categoryLabel);
    }

    const aliasValues: string[] = [];
    if (typeof definition.id === 'string') aliasValues.push(definition.id);
    if (typeof definition.name === 'string') aliasValues.push(definition.name);
    if (Array.isArray(definition.aliases)) {
      for (const alias of definition.aliases) {
        if (typeof alias === 'string') aliasValues.push(alias);
      }
    }

    for (const alias of aliasValues) {
      const trimmed = alias.trim();
      if (!trimmed) continue;
      const key = trimmed.toLocaleLowerCase();
      if (!byGroup.has(key)) {
        byGroup.set(key, { key: categoryKey, label: categoryLabel });
      }
    }
  }

  return { byGroup, categories };
}

type GroupingOptions = {
  ungroupedLabel: string;
  getGroupKey: (row: RowWithCost) => string | null | undefined;
  getGroupLabel?: (input: { key: string; raw: string; row: RowWithCost }) => string | null | undefined;
};

export function createGroups(
  rows: RowWithCost[],
  sortKey: keyof RowWithCost,
  asc: boolean,
  groupingMode: GroupingMode,
  labels: { ungroupedLabel: string; uncategorisedLabel: string },
  categoryLookup: ReturnType<typeof buildCategoryLookup>,
): ReadonlyArray<GroupedRows> {
  if (!rows.length) return [];

  if (groupingMode === 'flat') {
    return createGroupedRows(rows, sortKey, asc, {
      ungroupedLabel: '',
      getGroupKey: () => 'all',
      getGroupLabel: () => '',
    });
  }

  if (groupingMode === 'category') {
    return createGroupedRows(rows, sortKey, asc, {
      ungroupedLabel: labels.uncategorisedLabel,
      getGroupKey: (row) => {
        const base = row.grouping?.trim();
        if (!base) return null;
        const entry = categoryLookup.byGroup.get(base.toLocaleLowerCase());
        return entry?.key ?? null;
      },
      getGroupLabel: ({ key }) => categoryLookup.categories.get(key) ?? formatCategoryLabel(key),
    });
  }

  return createGroupedRows(rows, sortKey, asc, {
    ungroupedLabel: labels.ungroupedLabel,
    getGroupKey: (row) => row.grouping ?? null,
    getGroupLabel: ({ raw }) => raw,
  });
}

function createGroupedRows(
  rows: RowWithCost[],
  sortKey: keyof RowWithCost,
  asc: boolean,
  options: GroupingOptions,
): GroupedRows[] {
  const map = new Map<string, { key: string; label: string; rows: RowWithCost[] }>();
  const ordered: { key: string; label: string; rows: RowWithCost[] }[] = [];

  for (const row of rows) {
    const rawKey = options.getGroupKey(row);
    const trimmed = typeof rawKey === 'string' ? rawKey.trim() : '';
    const key = trimmed ? trimmed.toLocaleLowerCase() : UNGROUPED_KEY;
    let group = map.get(key);
    if (!group) {
      const label =
        key === UNGROUPED_KEY
          ? options.ungroupedLabel
          : options.getGroupLabel?.({ key, raw: trimmed, row }) ?? (trimmed || options.ungroupedLabel);
      group = { key, label, rows: [] };
      map.set(key, group);
      ordered.push(group);
    }
    group.rows.push(row);
  }

  const groups = ordered.map((group) => ({
    key: group.key,
    label: group.label,
    rows: group.rows,
    totals: calculateGroupTotals(group.rows, group.label),
  }));

  const totalsKey = GROUP_SUMMARY_SORT_MAP[sortKey];
  if (totalsKey) {
    groups.sort((a, b) => {
      const va = a.totals[totalsKey];
      const vb = b.totals[totalsKey];
      if (typeof va === 'string' || typeof vb === 'string') {
        const cmp = String(va ?? '').localeCompare(String(vb ?? ''));
        return asc ? cmp : -cmp;
      }
      const na = typeof va === 'number' && Number.isFinite(va) ? va : 0;
      const nb = typeof vb === 'number' && Number.isFinite(vb) ? vb : 0;
      if (na === nb) return 0;
      return asc ? na - nb : nb - na;
    });
  }

  return groups;
}

export function formatCategoryLabel(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '';
  return trimmed
    .split(/[^A-Za-z0-9]+/u)
    .filter(Boolean)
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(' ');
}

export function sanitizeGroupKey(key: string): string {
  const sanitized = key.replace(/[^a-zA-Z0-9_-]/g, '-');
  return sanitized || 'group';
}

export function calculateGroupTotals(rows: RowWithCost[], label: string): GroupTotals {
  const totalUnits = rows.reduce((sum, row) => sum + (row.units ?? 0), 0);
  const totalMarket = rows.reduce((sum, row) => sum + row.market_value_gbp, 0);
  const totalGain = rows.reduce((sum, row) => sum + row.gain_gbp, 0);
  const totalCost = rows.reduce((sum, row) => sum + row.cost, 0);
  const gainPct = Math.abs(totalCost) > 1e-9 ? (totalGain / totalCost) * 100 : null;

  const weightedAverage = (accessor: (row: RowWithCost) => number | null | undefined): number | null => {
    let numerator = 0;
    let denominator = 0;
    for (const row of rows) {
      const value = accessor(row);
      if (value == null || !Number.isFinite(value)) continue;
      const weight = row.market_value_gbp;
      if (!Number.isFinite(weight) || weight === 0) continue;
      numerator += value * weight;
      denominator += weight;
    }
    return denominator ? numerator / denominator : null;
  };

  return {
    labelValue: label,
    units: totalUnits,
    cost: totalCost,
    marketValue: totalMarket,
    gain: totalGain,
    gainPct,
    change7dPct: weightedAverage((row) => row.change_7d_pct),
    change30dPct: weightedAverage((row) => row.change_30d_pct),
  };
}

type StatusVariant = 'positive' | 'negative' | 'neutral';

const STATUS_CLASS_MAP: Record<StatusVariant, string> = {
  positive: statusStyles.positive,
  negative: statusStyles.negative,
  neutral: statusStyles.neutral,
};

export function cashFirstComparator(a: RowWithCost, b: RowWithCost): number {
  const aCash = isCashInstrument(a);
  const bCash = isCashInstrument(b);
  if (aCash && !bCash) return -1;
  if (!aCash && bCash) return 1;
  return 0;
}

function classifyStatus(value: number | null | undefined): StatusVariant {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) {
    return 'neutral';
  }
  return value > 0 ? 'positive' : 'negative';
}

export function getStatusPresentation(value: number | null | undefined): { className: string; prefix: string } {
  const variant = classifyStatus(value);
  const prefix = variant === 'positive' ? '▲' : variant === 'negative' ? '▼' : '';
  return { className: STATUS_CLASS_MAP[variant], prefix };
}

export function formatSignedMoney(value: number, currency: string): ReactNode {
  const { className, prefix } = getStatusPresentation(value);
  return <span className={className}>{`${prefix}${money(value, currency)}`}</span>;
}

export function formatSignedPercent(value: number | null | undefined): ReactNode {
  const { className, prefix } = getStatusPresentation(value);
  return <span className={className}>{`${prefix}${percent(value, 1)}`}</span>;
}

export function mergeGroupOptions(base: Iterable<string>, extras: Iterable<string | null | undefined>): string[] {
  const map = new Map<string, string>();
  for (const value of [...base, ...extras]) {
    if (typeof value !== 'string') continue;
    const trimmed = value.trim();
    if (!trimmed) continue;
    const key = trimmed.toLocaleLowerCase();
    if (!map.has(key)) map.set(key, trimmed);
  }
  return Array.from(map.values()).sort((a, b) => a.localeCompare(b));
}

export function splitTickerParts(value: string): { ticker: string; exchange: string } {
  const [sym, exch] = value.split('.', 2);
  const ticker = sym?.trim() ?? '';
  const exchange = (exch?.trim() ?? 'L') || 'L';
  return { ticker, exchange };
}

export function formatUnits(value: number): string {
  return new Intl.NumberFormat(i18n.language).format(value);
}
