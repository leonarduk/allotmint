import { useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import type { InstrumentSummary } from '../types';
import { InstrumentDetail } from './InstrumentDetail';
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
import {
  assignInstrumentGroup,
  clearInstrumentGroup,
  createInstrumentGroup,
  listInstrumentGroups,
} from '../api';

type Props = {
  rows: InstrumentSummary[];
};

type RowWithCost = InstrumentSummary & {
  cost: number;
  gain_pct: number;
};

type GroupTotals = {
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

const UNGROUPED_KEY = '__ungrouped__';

export function InstrumentTable({ rows }: Props) {
  const { t } = useTranslation();
  const { relativeViewEnabled, baseCurrency } = useConfig();
  const [selected, setSelected] = useState<InstrumentSummary | null>(null);
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

  const toggleColumn = (key: keyof typeof visibleColumns) => {
    setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const rowsWithCost = useMemo<RowWithCost[]>(
    () =>
      rows.map((r) => {
        const cost = r.market_value_gbp - r.gain_gbp;
        const gain_pct =
          r.gain_pct !== undefined && r.gain_pct !== null
            ? r.gain_pct
            : cost
              ? (r.gain_gbp / cost) * 100
              : 0;
        return { ...r, cost, gain_pct };
      }),
    [rows],
  );

  const { rows: sorted, sortKey, asc, handleSort } = useFilterableTable(
    rowsWithCost,
    'ticker',
    {},
  );

  const ungroupedLabel = t('instrumentTable.ungrouped', {
    defaultValue: 'Ungrouped',
  });
  const groups = useMemo<ReadonlyArray<GroupedRows>>(
    () => createGroupedRows(sorted, ungroupedLabel),
    [sorted, ungroupedLabel],
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
    setGroupOverrides({});
    setGroupOptions((prev) => mergeGroupOptions(prev, rows.map((r) => r.grouping ?? null)));
  }, [rows]);

  if (!rowsWithCost.length) {
    return <p>{t('instrumentTable.noInstruments')}</p>;
  }

  const columnLabels: [keyof typeof visibleColumns, string][] = [
    ['units', 'Units'],
    ['cost', 'Cost'],
    ['market', 'Market'],
    ['gain', 'Gain'],
    ['gain_pct', 'Gain %'],
  ];

  const assignmentLabel = t('instrumentTable.groupActions.placeholder', {
    defaultValue: 'Change…',
  });
  const savingLabel = t('instrumentTable.groupActions.saving', {
    defaultValue: 'Saving…',
  });
  const promptLabel = t('instrumentTable.groupActions.prompt', {
    defaultValue: 'Enter new group name',
  });

  return (
    <>
      <div style={{ marginBottom: '0.5rem' }}>
        <RelativeViewToggle />
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
          const expanded = expandedGroups.has(group.key);
          const toggleLabel = t('instrumentTable.groupToggle', {
            group: group.label,
            defaultValue: `Toggle ${group.label}`,
          });
          const groupDomId = `group-${sanitizeGroupKey(group.key)}`;
          const totalUnits = group.rows.reduce((sum, row) => sum + (row.units ?? 0), 0);
          const totalCost = group.rows.reduce((sum, row) => sum + row.cost, 0);

          return (
            <tbody key={group.key} id={groupDomId} className={tableStyles.groupSection}>
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
                    {totalUnits ? new Intl.NumberFormat(i18n.language).format(totalUnits) : '—'}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.cost && (
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {totalCost ? money(totalCost, baseCurrency) : '—'}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.market && (
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {money(group.totals.marketValue, baseCurrency)}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.gain && (
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {formatSignedMoney(group.totals.gain, baseCurrency)}
                  </td>
                )}
                {visibleColumns.gain_pct && (
                  <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                    {formatSignedPercent(group.totals.gainPct)}
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
                  {formatSignedPercent(group.totals.change7dPct)}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
                  {formatSignedPercent(group.totals.change30dPct)}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>
              </tr>
              {expanded &&
                group.rows.map((r) => {
                  const gainClass =
                    r.gain_gbp >= 0 ? statusStyles.positive : statusStyles.negative;
                  const gainPrefix = r.gain_gbp >= 0 ? '▲' : '▼';
                  const gainPctClass =
                    r.gain_pct != null && r.gain_pct >= 0
                      ? statusStyles.positive
                      : statusStyles.negative;
                  const gainPctPrefix =
                    r.gain_pct != null && r.gain_pct >= 0 ? '▲' : '▼';
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
                          onClick={() => setSelected(r)}
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
                              setSelected({
                                ticker: `${r.currency}GBP.FX`,
                                name: `${r.currency}GBP.FX`,
                                currency: r.currency,
                                instrument_type: 'FX',
                                units: 0,
                                market_value_gbp: 0,
                                gain_gbp: 0,
                              })
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
      </table>

      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          currency={selected.currency ?? undefined}
          instrument_type={selected.instrument_type}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

function createGroupedRows(rows: RowWithCost[], ungroupedLabel: string): GroupedRows[] {
  if (!rows.length) {
    return [];
  }

  const map = new Map<string, { key: string; label: string; rows: RowWithCost[] }>();
  const ordered: { key: string; label: string; rows: RowWithCost[] }[] = [];

  for (const row of rows) {
    const normalized = row.grouping?.trim();
    const key = normalized ? normalized : UNGROUPED_KEY;
    let group = map.get(key);
    if (!group) {
      group = {
        key,
        label: key === UNGROUPED_KEY ? ungroupedLabel : normalized ?? ungroupedLabel,
        rows: [],
      };
      map.set(key, group);
      ordered.push(group);
    }
    group.rows.push(row);
  }

  return ordered.map((group) => ({
    key: group.key,
    label: group.label,
    rows: group.rows,
    totals: calculateGroupTotals(group.rows),
  }));
}

function sanitizeGroupKey(key: string): string {
  const sanitized = key.replace(/[^a-zA-Z0-9_-]/g, '-');
  return sanitized || 'group';
}

function calculateGroupTotals(rows: RowWithCost[]): GroupTotals {
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
    marketValue: totalMarket,
    gain: totalGain,
    gainPct,
    change7dPct: weightedAverage((row) => row.change_7d_pct),
    change30dPct: weightedAverage((row) => row.change_30d_pct),
  };
}

function formatSignedMoney(value: number, currency: string): ReactNode {
  const isPositive = value >= 0;
  const prefix = isPositive ? '▲' : '▼';
  const className = isPositive ? statusStyles.positive : statusStyles.negative;
  return <span className={className}>{`${prefix}${money(value, currency)}`}</span>;
}

function formatSignedPercent(value: number | null | undefined): ReactNode {
  if (value == null || !Number.isFinite(value)) {
    return '—';
  }

  const isPositive = value >= 0;
  const prefix = isPositive ? '▲' : '▼';
  const className = isPositive ? statusStyles.positive : statusStyles.negative;
  return <span className={className}>{`${prefix}${percent(value, 1)}`}</span>;
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
