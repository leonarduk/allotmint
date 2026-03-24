import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import type { InstrumentGroupDefinition, InstrumentSummary } from '../types';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { money, percent } from '../lib/money';
import { translateInstrumentType } from '../lib/instrumentType';
import { formatDateISO } from '../lib/date';
import tableStyles from '../styles/table.module.css';
import { useConfig } from '../ConfigContext';
import { isSupportedFx } from '../lib/fx';
import { RelativeViewToggle } from './RelativeViewToggle';
import {
  assignInstrumentGroup,
  clearInstrumentGroup,
  createInstrumentGroup,
  listInstrumentGroups,
  listInstrumentGroupingDefinitions,
} from '../api';
import { useNavigate } from 'react-router-dom';
import { useInstrumentTableState } from './instrumentTable/useInstrumentTableState';
import {
  cashFirstComparator,
  createGroups,
  formatSignedMoney,
  formatSignedPercent,
  formatUnits,
  getStatusPresentation,
  mergeGroupOptions,
  sanitizeGroupKey,
  splitTickerParts,
  calculateGroupTotals,
} from './instrumentTable/utils';
import type { RowWithCost } from './instrumentTable/types';

type Props = {
  rows: InstrumentSummary[];
  showGroupTotals?: boolean;
};

export function InstrumentTable({ rows, showGroupTotals = true }: Props) {
  const { t } = useTranslation();
  const { relativeViewEnabled, baseCurrency } = useConfig();
  const [groupDefinitions, setGroupDefinitions] = useState<InstrumentGroupDefinition[]>([]);
  const navigate = useNavigate();
  const {
    categoryLookup,
    exchanges,
    expandedGroups,
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
  } = useInstrumentTableState(rows, groupDefinitions);

  const comparator = useCallback((a: RowWithCost, b: RowWithCost) => cashFirstComparator(a, b), []);
  const { rows: sorted, sortKey, asc, handleSort } = useFilterableTable(rowsWithCost, 'ticker', {}, comparator);

  const ungroupedLabel = t('instrumentTable.ungrouped', {
    defaultValue: 'Ungrouped',
  });
  const uncategorisedLabel = t('instrumentTable.uncategorised', {
    defaultValue: 'Uncategorised',
  });
  const groups = createGroups(sorted, sortKey, asc, groupingMode, {
    ungroupedLabel,
    uncategorisedLabel,
  }, categoryLookup);

  const handleGroupingModeChange = (value: string) => {
    if (value === 'group' || value === 'flat' || value === 'category') {
      setGroupingMode(value);
    }
  };

  const totalLabel = t('holdingsTable.totalRowLabel');
  const overallTotals = calculateGroupTotals(rowsWithCost, totalLabel);

  useEffect(() => {
    let cancelled = false;
    listInstrumentGroups()
      .then((fetched) => {
        if (cancelled) return;
        setGroupOptions(mergeGroupOptions([], fetched));
      })
      .catch((err) => {
        console.error('Failed to load instrument groups', err);
      });
    return () => {
      cancelled = true;
    };
  }, [setGroupOptions]);

  useEffect(() => {
    let cancelled = false;
    listInstrumentGroupingDefinitions()
      .then((fetched) => {
        if (cancelled) return;
        setGroupDefinitions(fetched);
      })
      .catch((err) => {
        console.error('Failed to load instrument group definitions', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);



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
                        ? formatUnits(group.totals.units)
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
                          {formatUnits(r.units)}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.cost && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {money(
                            r.cost,
                            r.market_value_currency || r.currency || baseCurrency,
                          )}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.market && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          {money(
                            r.market_value_gbp,
                            r.market_value_currency || r.currency || baseCurrency,
                          )}
                        </td>
                      )}
                      {!relativeViewEnabled && visibleColumns.gain && (
                        <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                          <span className={gainClass}>
                            {gainPrefix}
                            {money(
                              r.gain_gbp,
                              r.gain_currency || r.currency || baseCurrency,
                            )}
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
                                r.last_price_currency || r.currency || baseCurrency,
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
                        <div className={tableStyles.groupAction}>
                          <span className="shrink-0">{currentGrouping ?? '—'}</span>
                          <select
                            className={tableStyles.groupActionSelect}
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
                  ? formatUnits(overallTotals.units)
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
    console.error('Failed to assign group', err);
  } finally {
    setPending(null);
  }
}

