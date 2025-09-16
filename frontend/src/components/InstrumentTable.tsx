import { useMemo, useState, type ReactNode } from 'react';
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
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';

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
      {groups.map((group) => {
        const totals = (
          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <div className="flex items-baseline gap-1">
              <dt className="font-medium text-foreground">
                {t('instrumentTable.groupTotals.market', { defaultValue: 'Market' })}
              </dt>
              <dd>{money(group.totals.marketValue, baseCurrency)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt className="font-medium text-foreground">
                {t('instrumentTable.groupTotals.gain', { defaultValue: 'Gain' })}
              </dt>
              <dd>{formatSignedMoney(group.totals.gain, baseCurrency)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt className="font-medium text-foreground">
                {t('instrumentTable.groupTotals.gainPct', { defaultValue: 'Gain %' })}
              </dt>
              <dd>{formatSignedPercent(group.totals.gainPct)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt className="font-medium text-foreground">
                {t('instrumentTable.groupTotals.delta7d', { defaultValue: '7d %' })}
              </dt>
              <dd>{formatSignedPercent(group.totals.change7dPct)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt className="font-medium text-foreground">
                {t('instrumentTable.groupTotals.delta30d', { defaultValue: '30d %' })}
              </dt>
              <dd>{formatSignedPercent(group.totals.change30dPct)}</dd>
            </div>
          </dl>
        );

        return (
          <GroupCard key={group.key} title={group.label} totals={totals}>
            <table
              className={`${tableStyles.table} ${tableStyles.clickable}`}
              style={{ marginBottom: '0' }}
            >
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
                  <th className={tableStyles.cell}>
                    {t('instrumentTable.columns.ccy')}
                  </th>
                  <th className={tableStyles.cell}>
                    {t('instrumentTable.columns.type')}
                  </th>
                  {!relativeViewEnabled && visibleColumns.units && (
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t('instrumentTable.columns.units')}
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
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t('instrumentTable.columns.market')}
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
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t('instrumentTable.columns.last')}
                    </th>
                  )}
                  <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {t('instrumentTable.columns.lastDate')}
                  </th>
                  <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {t('instrumentTable.columns.delta7d')}
                  </th>
                  <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {t('instrumentTable.columns.delta30d')}
                  </th>
                </tr>
              </thead>

              <tbody>
                {group.rows.map((r) => {
                  const gainClass =
                    r.gain_gbp >= 0 ? statusStyles.positive : statusStyles.negative;
                  const gainPrefix = r.gain_gbp >= 0 ? '▲' : '▼';
                  const gainPctClass =
                    r.gain_pct != null && r.gain_pct >= 0
                      ? statusStyles.positive
                      : statusStyles.negative;
                  const gainPctPrefix =
                    r.gain_pct != null && r.gain_pct >= 0 ? '▲' : '▼';

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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </GroupCard>
        );
      })}

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

type GroupCardProps = {
  title: string;
  totals: ReactNode;
  children: ReactNode;
};

function GroupCard({ title, totals, children }: GroupCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <Card className="mb-4">
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-1 flex-col gap-2">
            <CardTitle>{title}</CardTitle>
            {totals}
          </div>
          <CollapsibleTrigger
            className="ml-auto text-sm"
            aria-label={open ? 'Collapse' : 'Expand'}
          >
            {open ? '−' : '+'}
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent>{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
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
