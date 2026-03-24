import { useEffect, useMemo, useState } from 'react';
import type { InstrumentGroupDefinition, InstrumentSummary } from '@/types';
import {
  buildCategoryLookup,
  collectExchanges,
  createRowsWithCost,
  filterRowsByExchange,
  mergeGroupOptions,
} from './utils';
import type { GroupingMode, VisibleColumns } from './types';

const DEFAULT_VISIBLE_COLUMNS: VisibleColumns = {
  units: true,
  cost: true,
  market: true,
  gain: true,
  gain_pct: true,
};

export function useInstrumentTableState(
  rows: InstrumentSummary[],
  groupDefinitions: InstrumentGroupDefinition[],
) {
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(DEFAULT_VISIBLE_COLUMNS);
  const [groupOptions, setGroupOptions] = useState<string[]>([]);
  const [groupOverrides, setGroupOverrides] = useState<Record<string, string | null | undefined>>({});
  const [pendingGroupTicker, setPendingGroupTicker] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set());
  const [groupingMode, setGroupingMode] = useState<GroupingMode>('group');

  const exchanges = useMemo(() => collectExchanges(rows), [rows]);
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(() => [...exchanges]);

  useEffect(() => {
    setSelectedExchanges((prev) => {
      const prevSet = new Set(prev);
      const availableSet = new Set(exchanges);
      let changed = false;
      const next: string[] = [];

      for (const value of prev) {
        if (availableSet.has(value)) {
          next.push(value);
        } else {
          changed = true;
        }
      }

      for (const value of exchanges) {
        if (!prevSet.has(value)) {
          next.push(value);
          changed = true;
        }
      }

      return changed ? next : prev;
    });
  }, [exchanges]);

  useEffect(() => {
    setGroupOverrides({});
    setGroupOptions((prev) => mergeGroupOptions(prev, rows.map((row) => row.grouping ?? null)));
  }, [rows]);

  useEffect(() => {
    if (!groupDefinitions.length) return;
    const names = groupDefinitions
      .map((definition) => {
        if (typeof definition.name === 'string' && definition.name.trim()) return definition.name;
        if (typeof definition.id === 'string' && definition.id.trim()) return definition.id;
        return null;
      })
      .filter((value): value is string => value !== null);
    if (!names.length) return;
    setGroupOptions((prev) => mergeGroupOptions(prev, names));
  }, [groupDefinitions]);

  const filteredRows = useMemo(
    () => filterRowsByExchange(rows, exchanges, selectedExchanges),
    [rows, exchanges, selectedExchanges],
  );
  const rowsWithCost = useMemo(() => createRowsWithCost(filteredRows), [filteredRows]);
  const categoryLookup = useMemo(() => buildCategoryLookup(groupDefinitions), [groupDefinitions]);
  const hasCategories = categoryLookup.categories.size > 0;

  useEffect(() => {
    if (groupingMode === 'category' && !hasCategories) {
      setGroupingMode('group');
    }
  }, [groupingMode, hasCategories]);

  const toggleExchangeSelection = (exchange: string) => {
    setSelectedExchanges((prev) => {
      const nextSet = new Set(prev);
      if (nextSet.has(exchange)) nextSet.delete(exchange);
      else nextSet.add(exchange);
      return exchanges.filter((value) => nextSet.has(value));
    });
  };

  const toggleColumn = (key: keyof VisibleColumns) => {
    setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return {
    categoryLookup,
    exchanges,
    expandedGroups,
    filteredRows,
    groupOptions,
    groupOverrides,
    groupingMode,
    hasCategories,
    pendingGroupTicker,
    rowsWithCost,
    selectedExchanges,
    setExpandedGroups,
    setGroupOptions,
    setGroupOverrides,
    setGroupingMode,
    setPendingGroupTicker,
    toggleColumn,
    toggleExchangeSelection,
    visibleColumns,
  };
}
