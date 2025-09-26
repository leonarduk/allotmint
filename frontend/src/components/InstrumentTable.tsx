import { useCallback, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import type { InstrumentGroupDefinition, InstrumentSummary } from '../types';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { money, percent } from '../lib/money';
import { translateInstrumentType } from '../lib/instrumentType';
import { formatDateISO } from '../lib/date';
import tableStyles from '../styles/table.module.css';
import statusStyles from '../styles/status.module.css';
import i18n from '../i18n';
import { useConfig } from '../ConfigContext';
import { isSupportedFx } from '../lib/fx';
import { RelativeViewToggle } from './RelativeViewToggle';
import { isCashInstrument } from '../lib/instruments';
import {
  assignInstrumentGroup,
  clearInstrumentGroup,
  createInstrumentGroup,
  listInstrumentGroups,
  listInstrumentGroupingDefinitions,
} from '../api';
import { useNavigate } from 'react-router-dom';

type Props = {
  rows: InstrumentSummary[];
  showGroupTotals?: boolean;
};

type RowWithCost = InstrumentSummary & {
  cost: number;
  gain_pct: number;
};

type GroupTotals = {
  labelValue: string;
  units: number;
  cost: number;
  marketValue: number;
  gain: number;
  gainPct: number | null;
  change7dPct: number | null;
  change30dPct: number | null;
};

type GroupedRows = {
  key: string;
  label: string;
  rows: RowWithCost[];
  totals: GroupTotals;
};

type GroupingMode = 'group' | 'flat' | 'category';

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

export function InstrumentTable({ rows, showGroupTotals = true }: Props) {
  const { t } = useTranslation();
  const { relativeViewEnabled, baseCurrency } = useConfig();
  const [visibleColumns, setVisibleColumns] = useState({
    units: true,
    cost: true,
    market: true,
    gain: true,
    gain_pct: true,
  });
  const [groupOptions, setGroupOptions] = useState<string[]>([]);
  const [groupOverrides, setGroupOverrides] = useState<Record<string, string | null | undefined>>({});
  const [pendingGroupTicker, setPendingGroupTicker] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set());
  const [groupDefinitions, setGroupDefinitions] = useState<InstrumentGroupDefinition[]>([]);
  const [groupingMode, setGroupingMode] = useState<GroupingMode>('group');
  const navigate = useNavigate();

  const exchanges = useMemo(() => {
    const values = new Set<string>();
    for (const row of rows) {
      const exchange = row.exchange?.trim();
      if (exchange) {
        values.add(exchange);
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [rows]);

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

      if (!changed) {
        return prev;
      }

      return next;
    });
  }, [exchanges]);

  const toggleExchangeSelection = (exchange: string) => {
    setSelectedExchanges((prev) => {
      const nextSet = new Set(prev);
      if (nextSet.has(exchange)) {
        nextSet.delete(exchange);
      } else {
        nextSet.add(exchange);
      }

      return exchanges.filter((value) => nextSet.has(value));
    });
  };

  const toggleColumn = (key: keyof typeof visibleColumns) => {
    setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const filteredRows = useMemo(
    () => {
      if (!rows.length) {
        return [];
      }
      if (!exchanges.length) {
        return rows;
      }
      if (!selectedExchanges.length) {
        return [];
      }
      const selectedSet = new Set(selectedExchanges);
      return rows.filter((row) => {
        const exchange = row.exchange?.trim();
        if (!exchange) {
          return true;
        }
        return selectedSet.has(exchange);
      });
    },
    [rows, exchanges, selectedExchanges],
  );

  const rowsWithCost = useMemo<RowWithCost[]>(
    () =>
      filteredRows.map((r) => {
        const cost = r.market_value_gbp - r.gain_gbp;
        const gain_pct =
          r.gain_pct !== undefined && r.gain_pct !== null
            ? r.gain_pct
            : cost
              ? (r.gain_gbp / cost) * 100
              : 0;
        return { ...r, cost, gain_pct };
      }),
    [filteredRows],
  );

  const categoryLookup = useMemo(
    () => {
      const byGroup = new Map<string, { key: string; label: string }>();
      const categories = new Map<string, string>();

      for (const definition of groupDefinitions) {
        const rawCategory =
          typeof definition.category === 'string' ? definition.category.trim() : '';
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
        if (typeof definition.id === 'string') {
          aliasValues.push(definition.id);
        }
        if (typeof definition.name === 'string') {
          aliasValues.push(definition.name);
        }
        if (Array.isArray(definition.aliases)) {
          for (const alias of definition.aliases) {
            if (typeof alias === 'string') {
              aliasValues.push(alias);
            }
          }
        }

        for (const alias of aliasValues) {
          const trimmed = alias.trim();
          if (!trimmed) continue;
          const key = trimmed.toLocaleLowerCase();
          if (!key) continue;
          if (!byGroup.has(key)) {
            byGroup.set(key, { key: categoryKey, label: categoryLabel });
          }
        }
      }

      return { byGroup, categories };
    },
    [groupDefinitions],
  );

  const cashFirstComparator = useCallback(
    (
      a: RowWithCost,
      b: RowWithCost,
      _sortKey: keyof RowWithCost,
      _asc: boolean,
    ) => {
      const aCash = isCashInstrument(a);
      const bCash = isCashInstrument(b);
      if (aCash && !bCash) {
        return -1;
      }
      if (!aCash && bCash) {
        return 1;
      }
      return 0;
    },
    [],
  );

  const { rows: sorted, sortKey, asc, handleSort } = useFilterableTable(
    rowsWithCost,
    'ticker',
    {},
    cashFirstComparator,
  );

  const ungroupedLabel = t('instrumentTable.ungrouped', {
    defaultValue: 'Ungrouped',
  });
  const uncategorisedLabel = t('instrumentTable.uncategorised', {
    defaultValue: 'Uncategorised',
  });
  const groups = useMemo<ReadonlyArray<GroupedRows>>(() => {
    if (!sorted.length) {
      return [];
    }
    if (groupingMode === 'flat') {
      return createGroupedRows(sorted, sortKey, asc, {
        ungroupedLabel: '',
        getGroupKey: () => 'all',
        getGroupLabel: () => '',
      });
    }
    if (groupingMode === 'category') {
      return createGroupedRows(sorted, sortKey, asc, {
        ungroupedLabel: uncategorisedLabel,
        getGroupKey: (row) => {
          const base = row.grouping?.trim();
          if (!base) return null;
          const entry = categoryLookup.byGroup.get(base.toLocaleLowerCase());
          return entry?.key ?? null;
        },
        getGroupLabel: ({ key }) =>
          categoryLookup.categories.get(key) ?? formatCategoryLabel(key),
      });
    }
    return createGroupedRows(sorted, sortKey, asc, {
      ungroupedLabel,
      getGroupKey: (row) => row.grouping ?? null,
      getGroupLabel: ({ raw }) => raw,
    });
  }, [asc, categoryLookup, groupingMode, sorted, sortKey, uncategorisedLabel, ungroupedLabel]);

  const hasCategories = categoryLookup.categories.size > 0;

  useEffect(() => {
    if (groupingMode === 'category' && !hasCategories) {
      setGroupingMode('group');
    }
  }, [groupingMode, hasCategories]);

  const handleGroupingModeChange = (value: string) => {
    if (value === 'group' || value === 'flat' || value === 'category') {
      setGroupingMode(value);
    }
  };

  const totalLabel = t('holdingsTable.totalRowLabel');

  const overallTotals = useMemo(
    () => calculateGroupTotals(rowsWithCost, totalLabel),
    [rowsWithCost, totalLabel],
  );

  useEffect(() => {
    let cancelled = false;
    listInstrumentGroups()
      .then((fetched) => {
        if (cancelled) return;
        setGroupOptions(mergeGroupOptions([], fetched));
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error('Failed to load instrument groups', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    listInstrumentGroupingDefinitions()
      .then((fetched) => {
        if (cancelled) return;
        setGroupDefinitions(fetched);
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error('Failed to load instrument group definitions', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setGroupOverrides({});
    setGroupOptions((prev) => mergeGroupOptions(prev, rows.map((r) => r.grouping ?? null)));
  }, [rows]);

  useEffect(() => {
    if (!groupDefinitions.length) {
      return;
    }
    const names = groupDefinitions
      .map((definition) => {
        if (typeof definition.name === 'string' && definition.name.trim()) {
          return definition.name;
        }
        if (typeof definition.id === 'string' && definition.id.trim()) {
          return definition.id;
        }
        return null;
      })
      .filter((value): value is string => value !== null);
    if (!names.length) {
      return;
    }
    setGroupOptions((prev) => mergeGroupOptions(prev, names));
  }, [groupDefinitions]);

  if (!rows.length) {
    return <p>{t('instrumentTable.noInstruments')}</p>;
  }

  const noFilteredRows = rowsWithCost.length === 0;
  const columnLabels: [keyof typeof visibleColumns, string][] = [
    ['units', 'Units'],
    ['cost', 'Cost'],
    ['market', 'Market'],
    ['gain', 'Gain'],
    ['gain_pct', 'Gain %'],
  ];

  const exchangeLabel = t('instrumentTable.exchangesLabel', {
    defaultValue: 'Exchanges:',
  });
  const assignmentLabel = t('instrumentTable.groupActions.placeholder', {
    defaultValue: 'Change…',
  });
  const savingLabel = t('instrumentTable.groupActions.saving', {
    defaultValue: 'Saving…',
  });
  const promptLabel = t('instrumentTable.groupActions.prompt', {
    defaultValue: 'Enter new group name',
  });
  const showGroupHeaders = groupingMode !== 'flat';
  const viewModeLabel = t('instrumentTable.viewModeLabel', { defaultValue: 'View:' });
  const groupedOptionLabel = t('instrumentTable.viewMode.grouped', {
    defaultValue: 'Group totals',
  });
  const categoryOptionLabel = t('instrumentTable.viewMode.category', {
    defaultValue: 'By category',
  });
  const flatOptionLabel = t('instrumentTable.viewMode.flat', {
    defaultValue: 'Flat list',
  });
  const showCategoryOption = hasCategories;

  return (
    <>
      <div style={{ marginBottom: '0.5rem' }}>
        <RelativeViewToggle />
      </div>
      {exchanges.length > 0 && (
        <fieldset
          style={{
            marginBottom: '0.5rem',
            border: 'none',
            padding: 0,
          }}
        >
          <legend>{exchangeLabel}</legend>
          {exchanges.map((exchange) => {
            const checkboxId = `instrument-table-exchange-${exchange}`;
            return (
              <label key={exchange} htmlFor={checkboxId} style={{ marginRight: '0.75rem' }}>
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={selectedExchanges.includes(exchange)}
                  onChange={() => toggleExchangeSelection(exchange)}
                />
                {exchange}
              </label>
            );
          })}
        </fieldset>
      )}
      <div style={{ marginBottom: '0.5rem' }}>
        {viewModeLabel}
        <select
          value={groupingMode}
          onChange={(event) => handleGroupingModeChange(event.target.value)}
          style={{ marginLeft: '0.5rem' }}
        >
          <option value="group">{groupedOptionLabel}</option>
          {showCategoryOption && (
            <option value="category">{categoryOptionLabel}</option>
          )}
          <option value="flat">{flatOptionLabel}</option>
        </select>
      </div>
      <div style={{ marginBottom: '0.5rem' }}>
        Columns:
        {columnLabels.map(([key, label]) => (
          <label key={key} style={{ marginLeft: '0.5rem' }}>
            <input
              type="checkbox"
              checked={visibleColumns[key]}
              onChange={() => toggleColumn(key)}
            />
            {label}
          </label>
        ))}
      </div>
      {noFilteredRows ? (
        <p>{t('instrumentTable.noInstruments')}</p>
      ) : (
        <table className={`${tableStyles.table} ${tableStyles.clickable}`} style={{ marginBottom: '0' }}>
        <thead>
          <tr>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort('ticker')}
            >
              {t('instrumentTable.columns.ticker')}
              {sortKey === 'ticker' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort('name')}
            >
              {t('instrumentTable.columns.name')}
              {sortKey === 'name' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort('currency')}
            >
              {t('instrumentTable.columns.ccy')}
              {sortKey === 'currency' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort('instrument_type')}
            >
              {t('instrumentTable.columns.type')}
              {sortKey === 'instrument_type' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            {!relativeViewEnabled && visibleColumns.units && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('units')}
              >
                {t('instrumentTable.columns.units')}
                {sortKey === 'units' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            {!relativeViewEnabled && visibleColumns.cost && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('cost')}
              >
                {t('instrumentTable.columns.cost')}
                {sortKey === 'cost' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            {!relativeViewEnabled && visibleColumns.market && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('market_value_gbp')}
              >
                {t('instrumentTable.columns.market')}
                {sortKey === 'market_value_gbp' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            {!relativeViewEnabled && visibleColumns.gain && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('gain_gbp')}
              >
                {t('instrumentTable.columns.gain')}
                {sortKey === 'gain_gbp' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            {visibleColumns.gain_pct && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('gain_pct')}
              >
                {t('instrumentTable.columns.gainPct')}
                {sortKey === 'gain_pct' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            {!relativeViewEnabled && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort('last_price_gbp')}
              >
                {t('instrumentTable.columns.last')}
                {sortKey === 'last_price_gbp' ? (asc ? ' ▲' : ' ▼') : ''}
              </th>
            )}
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort('last_price_date')}
            >
              {t('instrumentTable.columns.lastDate')}
              {sortKey === 'last_price_date' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort('change_7d_pct')}
            >
              {t('instrumentTable.columns.delta7d')}
              {sortKey === 'change_7d_pct' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort('change_30d_pct')}
            >
              {t('instrumentTable.columns.delta30d')}
              {sortKey === 'change_30d_pct' ? (asc ? ' ▲' : ' ▼') : ''}
            </th>
            <th className={tableStyles.cell}>
              {t('instrumentTable.columns.groupActions', { defaultValue: 'Group' })}
            </th>
          </tr>
        </thead>
        {groups.map((group) => {
          const expanded = showGroupHeaders ? expandedGroups.has(group.key) : true;
          const toggleLabel = t('instrumentTable.groupToggle', {
            group: group.label,
            defaultValue: `Toggle ${group.label}`,
          });
          const groupDomId = `group-${sanitizeGroupKey(group.key)}`;
          return (
            <tbody key={group.key} id={groupDomId} className={tableStyles.groupSection}>
              {showGroupHeaders && (
                <tr className={tableStyles.groupRow}>
                  <th
                    scope="row"
                    className={`${tableStyles.cell} ${tableStyles.groupCell}`}
                    colSpan={2}
                  >
                    <button
                      type="button"
                      className={tableStyles.groupToggle}
                      onClick={() =>
                        setExpandedGroups((prev) => {
                          const next = new Set(prev);
                          if (next.has(group.key)) {
                            next.delete(group.key);
                          } else {
                            next.add(group.key);
                          }
                          return next;
                        })
                      }
                      aria-expanded={expanded}
                      aria-controls={groupDomId}
                      aria-label={toggleLabel}
                    >
                      <span aria-hidden="true" className={tableStyles.groupToggleIcon}>
                        {expanded ? '−' : '+'}
                      </span>
                      <span>{group.label}</span>
                      <span className={tableStyles.groupCount}>
                        ({group.rows.length})
                      </span>
                    </button>
                  </th>
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>
                  {!relativeViewEnabled && visibleColumns.units && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      {showGroupTotals && Number.isFinite(group.totals.units)
                        ? new Intl.NumberFormat(i18n.language).format(group.totals.units)
                        : '—'}
                    </td>
                  )}
                  {!relativeViewEnabled && visibleColumns.cost && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      {showGroupTotals && Number.isFinite(group.totals.cost)
                        ? money(group.totals.cost, baseCurrency)
                        : '—'}
                    </td>
                  )}
                  {!relativeViewEnabled && visibleColumns.market && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      {showGroupTotals && Number.isFinite(group.totals.marketValue)
                        ? money(group.totals.marketValue, baseCurrency)
                        : '—'}
                    </td>
                  )}
                  {!relativeViewEnabled && visibleColumns.gain && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      {showGroupTotals && Number.isFinite(group.totals.gain)
                        ? formatSignedMoney(group.totals.gain, baseCurrency)
                        : '—'}
                    </td>
                  )}
                  {visibleColumns.gain_pct && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      {showGroupTotals ? formatSignedPercent(group.totals.gainPct) : '—'}
                    </td>
                  )}
                  {!relativeViewEnabled && (
                    <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                      —
                    </td>
                  )}
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    —
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {showGroupTotals ? formatSignedPercent(group.totals.change7dPct) : '—'}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {showGroupTotals ? formatSignedPercent(group.totals.change30dPct) : '—'}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>
                </tr>
              )}
              {(showGroupHeaders ? expanded : true) &&
                group.rows.map((r) => {
                  const { className: gainClass, prefix: gainPrefix } =
                    getStatusPresentation(r.gain_gbp);
                  const { className: gainPctClass, prefix: gainPctPrefix } =
                    getStatusPresentation(r.gain_pct);
                  const overrideExists = Object.prototype.hasOwnProperty.call(
                    groupOverrides,
                    r.ticker,
                  );
                  const currentGrouping = overrideExists
                    ? groupOverrides[r.ticker] ?? null
                    : r.grouping ?? null;
                  const availableGroups = mergeGroupOptions(groupOptions, [currentGrouping]);

                  return (
                    <tr key={`${group.key}-${r.ticker}`}>
                      <td className={tableStyles.cell}>
                        <button
                          type="button"
                          onClick={() => navigate(`/research/${encodeURIComponent(r.ticker)}`)}
                          style={{
                            color: 'dodgerblue',
                            textDecoration: 'underline',
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            font: 'inherit',
                            cursor: 'pointer',
                          }}
                        >
                          {r.ticker}
                        </button>
                      </td>
                      <td className={tableStyles.cell}>{r.name}</td>
                      <td className={tableStyles.cell}>
                        {isSupportedFx(r.currency) ? (
                          <button
                            type="button"
                            onClick={() =>
                              navigate(
                                `/research/${encodeURIComponent(`${r.currency}GBP.FX`)}`,
                              )
                            }
                            style={{
                              color: 'dodgerblue',
                              textDecoration: 'underline',
                              background: 'none',
                              border: 'none',
                              padding: 0,
                              font: 'inherit',
                              cursor: 'pointer',
                            }}
                          >
                            {r.currency}
                          </button>
                        ) : (
                          r.currency ?? '—'
                        )}
                      </td>
                      <td className={tableStyles.cell}>
                        {translateInstrumentType(t, r.instrument_type)}
                      </td>
                      {!relativeViewEnabled && visibleColumns.units && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {new Intl.NumberFormat(i18n.language).format(r.units)}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.cost && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {money(r.cost, r.market_value_currency || baseCurrency)}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.market && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {money(
                            r.market_value_gbp,
                            r.market_value_currency || baseCurrency,
                          )}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.gain && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          <span className={gainClass}>
                            {gainPrefix}
                            {money(r.gain_gbp, r.gain_currency || baseCurrency)}
                          </span>
                        </td>
                      )}
                      {visibleColumns.gain_pct && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          <span className={gainPctClass}>
                            {gainPctPrefix}
                            {percent(r.gain_pct, 1)}
                          </span>
                        </td>
                      )}
                      {!relativeViewEnabled && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {r.last_price_gbp != null
                            ? money(
                                r.last_price_gbp,
                                r.last_price_currency || baseCurrency,
                              )
                            : '—'}
                        </td>
                      )}
                      <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                        {r.last_price_date
                          ? formatDateISO(new Date(r.last_price_date))
                          : '—'}
                      </td>
                      <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                        {r.change_7d_pct == null ? '—' : percent(r.change_7d_pct, 1)}
                      </td>
                      <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                        {r.change_30d_pct == null
                          ? '—'
                          : percent(r.change_30d_pct, 1)}
                      </td>
                      <td className={tableStyles.cell}>
                        <div className="flex flex-col gap-1">
                          <span>{currentGrouping ?? '—'}</span>
                          <select
                            aria-label={t('instrumentTable.groupActions.ariaLabel', {
                              ticker: r.ticker,
                              defaultValue: `Change group for ${r.ticker}`,
                            })}
                            value=""
                            onChange={async (event) => {
                              const value = event.target.value;
                              event.target.value = '';
                              await handleGroupSelection(
                                r.ticker,
                                value,
                                setGroupOptions,
                                setGroupOverrides,
                                setPendingGroupTicker,
                                promptLabel,
                              );
                            }}
                            disabled={pendingGroupTicker === r.ticker}
                          >
                            <option value="" disabled>
                              {pendingGroupTicker === r.ticker ? savingLabel : assignmentLabel}
                            </option>
                            <option value="__clear__">
                              {t('instrumentTable.groupActions.clear', {
                                defaultValue: 'Clear assignment',
                              })}
                            </option>
                            {availableGroups.map((option) => (
                              <option key={option} value={option}>
                                {t('instrumentTable.groupActions.assign', {
                                  group: option,
                                  defaultValue: `Assign to ${option}`,
                                })}
                              </option>
                            ))}
                            <option value="__create__">
                              {t('instrumentTable.groupActions.create', {
                                defaultValue: 'Create new group…',
                              })}
                            </option>
                          </select>
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          );
        })}
        <tfoot>
          <tr>
            <td className={`${tableStyles.cell} font-semibold`} colSpan={4}>
              {totalLabel}
            </td>
            {!relativeViewEnabled && visibleColumns.units && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {Number.isFinite(overallTotals.units)
                  ? new Intl.NumberFormat(i18n.language).format(overallTotals.units)
                  : '—'}
              </td>
            )}
            {!relativeViewEnabled && visibleColumns.cost && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {Number.isFinite(overallTotals.cost)
                  ? money(overallTotals.cost, baseCurrency)
                  : '—'}
              </td>
            )}
            {!relativeViewEnabled && visibleColumns.market && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {Number.isFinite(overallTotals.marketValue)
                  ? money(overallTotals.marketValue, baseCurrency)
                  : '—'}
              </td>
            )}
            {!relativeViewEnabled && visibleColumns.gain && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {Number.isFinite(overallTotals.gain)
                  ? formatSignedMoney(overallTotals.gain, baseCurrency)
                  : '—'}
              </td>
            )}
            {visibleColumns.gain_pct && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {formatSignedPercent(overallTotals.gainPct)}
              </td>
            )}
            {!relativeViewEnabled && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                —
              </td>
            )}
            <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
              —
            </td>
            <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
              {formatSignedPercent(overallTotals.change7dPct)}
            </td>
            <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
              {formatSignedPercent(overallTotals.change30dPct)}
            </td>
            <td className={`${tableStyles.cell} font-semibold`}>—</td>
          </tr>
        </tfoot>
        </table>
      )}

    </>
  );
}

type GroupingOptions = {
  ungroupedLabel: string;
  getGroupKey: (row: RowWithCost) => string | null | undefined;
  getGroupLabel?: (input: { key: string; raw: string; row: RowWithCost }) =>
    | string
    | null
    | undefined;
};

function createGroupedRows(
  rows: RowWithCost[],
  sortKey: keyof RowWithCost,
  asc: boolean,
  options: GroupingOptions,
): GroupedRows[] {
  if (!rows.length) {
    return [];
  }

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
          : options.getGroupLabel?.({
                key,
                raw: trimmed,
                row,
              }) ?? (trimmed || options.ungroupedLabel);
      group = {
        key,
        label,
        rows: [],
      };
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
        const sa = typeof va === 'string' ? va : '';
        const sb = typeof vb === 'string' ? vb : '';
        const cmp = sa.localeCompare(sb);
        return asc ? cmp : -cmp;
      }

      const toNumeric = (value: unknown) =>
        typeof value === 'number' && Number.isFinite(value) ? value : 0;

      const na = toNumeric(va);
      const nb = toNumeric(vb);
      if (na === nb) {
        return 0;
      }
      return asc ? na - nb : nb - na;
    });
  }

  return groups;
}

function formatCategoryLabel(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  return trimmed
    .split(/[^A-Za-z0-9]+/u)
    .filter(Boolean)
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(' ');
}

function sanitizeGroupKey(key: string): string {
  const sanitized = key.replace(/[^a-zA-Z0-9_-]/g, '-');
  return sanitized || 'group';
}

function calculateGroupTotals(rows: RowWithCost[], label: string): GroupTotals {
  const totalUnits = rows.reduce((sum, row) => sum + (row.units ?? 0), 0);
  const totalMarket = rows.reduce((sum, row) => sum + row.market_value_gbp, 0);
  const totalGain = rows.reduce((sum, row) => sum + row.gain_gbp, 0);
  const totalCost = rows.reduce((sum, row) => sum + row.cost, 0);

  const gainPct = Math.abs(totalCost) > 1e-9 ? (totalGain / totalCost) * 100 : null;

  const weightedAverage = (
    accessor: (row: RowWithCost) => number | null | undefined,
  ): number | null => {
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

function classifyStatus(value: number | null | undefined): StatusVariant {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) {
    return 'neutral';
  }

  return value > 0 ? 'positive' : 'negative';
}

function getStatusPresentation(
  value: number | null | undefined,
): { className: string; prefix: string } {
  const variant = classifyStatus(value);
  const prefix = variant === 'positive' ? '▲' : variant === 'negative' ? '▼' : '';

  return { className: STATUS_CLASS_MAP[variant], prefix };
}

function formatSignedMoney(value: number, currency: string): ReactNode {
  const { className, prefix } = getStatusPresentation(value);
  const display = money(value, currency);
  return <span className={className}>{`${prefix}${display}`}</span>;
}

function formatSignedPercent(value: number | null | undefined): ReactNode {
  const { className, prefix } = getStatusPresentation(value);
  const display = percent(value, 1);
  return <span className={className}>{`${prefix}${display}`}</span>;
}

type GroupOverridesMap = Record<string, string | null | undefined>;

async function handleGroupSelection(
  fullTicker: string,
  selection: string,
  setOptions: Dispatch<SetStateAction<string[]>>,
  setOverrides: Dispatch<SetStateAction<GroupOverridesMap>>,
  setPending: Dispatch<SetStateAction<string | null>>,
  promptText: string,
): Promise<void> {
  if (!selection) return;
  const { ticker, exchange } = splitTickerParts(fullTicker);
  if (!ticker) return;

  if (selection === '__create__') {
    const name = window.prompt(promptText);
    const trimmed = name?.trim();
    if (!trimmed) {
      return;
    }
    setPending(fullTicker);
    try {
      const created = await createInstrumentGroup(trimmed);
      setOptions(() => mergeGroupOptions([], created.groups));
      const assigned = await assignInstrumentGroup(ticker, exchange, created.group);
      const applied = assigned.group ?? created.group;
      setOverrides((prev) => ({ ...prev, [fullTicker]: applied }));
      if (assigned.groups?.length) {
        setOptions(() => mergeGroupOptions([], assigned.groups));
      } else {
        setOptions((prev) => mergeGroupOptions(prev, [applied]));
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Failed to create group', err);
    } finally {
      setPending(null);
    }
    return;
  }

  if (selection === '__clear__') {
    setPending(fullTicker);
    try {
      await clearInstrumentGroup(ticker, exchange);
      setOverrides((prev) => ({ ...prev, [fullTicker]: null }));
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Failed to clear group', err);
    } finally {
      setPending(null);
    }
    return;
  }

  setPending(fullTicker);
  try {
    const assigned = await assignInstrumentGroup(ticker, exchange, selection);
    const applied = assigned.group ?? selection;
    setOverrides((prev) => ({ ...prev, [fullTicker]: applied }));
    if (assigned.groups?.length) {
      setOptions(() => mergeGroupOptions([], assigned.groups));
    } else {
      setOptions((prev) => mergeGroupOptions(prev, [applied]));
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('Failed to assign group', err);
  } finally {
    setPending(null);
  }
}

function mergeGroupOptions(
  base: Iterable<string>,
  extras: Iterable<string | null | undefined>,
): string[] {
  const map = new Map<string, string>();
  for (const value of base) {
    if (typeof value !== 'string') continue;
    const trimmed = value.trim();
    if (!trimmed) continue;
    const key = trimmed.toLocaleLowerCase();
    if (!map.has(key)) map.set(key, trimmed);
  }
  for (const value of extras) {
    if (typeof value !== 'string') continue;
    const trimmed = value.trim();
    if (!trimmed) continue;
    const key = trimmed.toLocaleLowerCase();
    if (!map.has(key)) map.set(key, trimmed);
  }
  return Array.from(map.values()).sort((a, b) => a.localeCompare(b));
}

function splitTickerParts(value: string): { ticker: string; exchange: string } {
  const [sym, exch] = value.split('.', 2);
  const ticker = sym?.trim() ?? '';
  const exchange = (exch?.trim() ?? 'L') || 'L';
  return { ticker, exchange };
}
