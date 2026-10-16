import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getIndexSummary } from '../api';
import { useFetch } from '../hooks/useFetch';
import i18n from '../i18n';
import { percent } from '../lib/money';
import tableStyles from '../styles/table.module.css';
import type {
  IndexSummaryRow,
  IndexTotalReturn,
  IndexWindowChange,
} from '../types';

// Matches the owner table's 1W/1M/1Y/3Y columns, in the same order.
const PERIOD_WINDOWS = ['1W', '1M', '1Y', '3Y'] as const;
// Matches the owner table's 1Y/3Y total return columns, in the same order.
const TOTAL_RETURN_FIELDS = ['total_return_1y', 'total_return_3y'] as const;
// Index levels move slowly and the backend caches for 5 minutes too.
const INDEX_SUMMARY_TTL_MS = 5 * 60_000;

// Module-level so ``useFetch`` sees one stable function, not a new one per render.
const fetchIndexSummary = () => getIndexSummary();

const cell = `${tableStyles.cell} ${tableStyles.right}`;

// Index levels are points, not money: two decimals, no currency symbol.
const points = (v: number, signed = false): string => {
  const text = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v);
  return signed && v > 0 ? `+${text}` : text;
};

// Coloured by the GBP move, what a sterling investor got; none without one.
const changeColor = (window: IndexWindowChange | null): string | undefined =>
  window?.pct == null
    ? undefined
    : window.pct >= 0
      ? 'var(--gain-positive)'
      : 'var(--gain-negative)';

/** Owner-table columns an index has no figure for: stock/cash split, total return £. */
const BlankCells = ({ count }: { count: number }) => (
  <>
    {Array.from({ length: count }, (_, i) => (
      <td key={i} className={cell} />
    ))}
  </>
);

type RowProps = { row: IndexSummaryRow; relative: boolean };

function IndexRow({ row, relative }: RowProps) {
  const { t } = useTranslation();
  const day = row.changes['1D'];
  // A converted level says what it was before conversion, beside its date.
  const levelTitle =
    [
      row.as_of,
      row.currency === 'GBP'
        ? null
        : t('group.indexRows.levelConvertedFrom', {
            value: points(row.value),
            currency: row.currency,
          }),
    ]
      .filter(Boolean)
      .join(' · ') || undefined;
  // A converted move says what it was before conversion.
  const convertedTitle = (window: IndexWindowChange | null) =>
    window === null || row.currency === 'GBP'
      ? undefined
      : t('group.indexRows.convertedFrom', {
          value: `${points(window.local_change, true)} (${percent(window.local_pct)})`,
          currency: row.currency,
        });
  return (
    <tr data-testid={`index-row-${row.symbol}`}>
      <td
        className={tableStyles.cell}
        style={{ paddingLeft: '1.75rem', fontSize: '0.9rem' }}
      >
        {row.name}
      </td>
      {/* Relative view's "Portfolio %" has no meaning for an index. */}
      <td className={cell} title={levelTitle}>
        {relative ? '' : row.value_gbp === null ? '—' : points(row.value_gbp)}
      </td>
      <BlankCells count={2} />
      {!relative && (
        <td
          className={cell}
          style={{ color: changeColor(day) }}
          title={convertedTitle(day)}
        >
          {day?.change == null ? '—' : points(day.change, true)}
        </td>
      )}
      <td
        className={cell}
        style={{ color: changeColor(day) }}
        title={convertedTitle(day)}
      >
        {percent(day?.pct)}
      </td>
      {PERIOD_WINDOWS.map((key) => {
        const window = row.changes[key];
        return (
          <td
            key={key}
            className={cell}
            style={{ color: changeColor(window) }}
            title={convertedTitle(window)}
          >
            {window?.change == null
              ? '—'
              : relative
                ? percent(window.pct)
                : `${points(window.change, true)} (${percent(window.pct)})`}
          </td>
        );
      })}
      {/* Total Return £ has no meaning for an index; only the % is shown. */}
      {TOTAL_RETURN_FIELDS.map((field) => (
        <Fragment key={field}>
          {!relative && <BlankCells count={1} />}
          {/* ``?? null``: a backend older than the 3Y figure omits the field. */}
          <TotalReturnCell totalReturn={row[field] ?? null} />
        </Fragment>
      ))}
    </tr>
  );
}

function TotalReturnCell({
  totalReturn,
}: {
  totalReturn: IndexTotalReturn | null;
}) {
  const { t } = useTranslation();
  if (totalReturn === null) return <td className={cell}>—</td>;
  const source =
    totalReturn.source === 'index'
      ? t('group.indexRows.totalReturnSourceIndex', {
          symbol: totalReturn.symbol,
        })
      : t('group.indexRows.totalReturnSourceEtf', {
          symbol: totalReturn.symbol,
          fee: percent(totalReturn.fee_pct),
        });
  const title =
    totalReturn.local_currency === 'GBP'
      ? source
      : `${source}. ${t('group.indexRows.convertedFrom', {
          value: percent(totalReturn.local_pct),
          currency: totalReturn.local_currency,
        })}`;
  return (
    <td
      className={cell}
      title={title}
      style={{
        color:
          totalReturn.pct >= 0
            ? 'var(--gain-positive)'
            : 'var(--gain-negative)',
      }}
    >
      {percent(totalReturn.pct)}
    </td>
  );
}

type Props = { relativeViewEnabled: boolean };

/**
 * Benchmark index rows for the owner summary table: an "Indices" pseudo-owner
 * whose "accounts" are FTSE 100, FTSE 250, S&P 500 and NASDAQ-100. Levels and
 * changes are in index points with price-return %; 1Y/3Y Total Return % add
 * reinvested dividends. The money-only columns (stock/cash split, total
 * return £) stay blank and the group row itself has no aggregate: summing
 * index levels means nothing.
 */
export function IndexBenchmarkRows({ relativeViewEnabled }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const { data, loading, error } = useFetch(fetchIndexSummary, [], true, {
    cacheKey: 'market-index-summary',
    ttlMs: INDEX_SUMMARY_TTL_MS,
  });
  const colCount = relativeViewEnabled ? 11 : 14;
  const rows = data?.indexes ?? [];

  let status: string | null = null;
  if (error) status = t('group.indexRows.error');
  else if (loading && !data) status = t('group.indexRows.loading');
  else if (rows.length === 0) status = t('group.indexRows.empty');

  return (
    <Fragment>
      <tr
        className={tableStyles.clickable}
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        title={t('group.indexRows.help')}
      >
        <td className={tableStyles.cell}>
          <span style={{ marginRight: '0.5rem' }}>{expanded ? '▾' : '▸'}</span>
          {t('group.indexRows.label')}
        </td>
        <BlankCells count={colCount - 1} />
      </tr>
      {expanded && status !== null && (
        <tr>
          <td
            className={tableStyles.cell}
            colSpan={colCount}
            style={{ paddingLeft: '1.75rem' }}
          >
            {status}
          </td>
        </tr>
      )}
      {expanded &&
        status === null &&
        rows.map((row) => (
          <IndexRow key={row.symbol} row={row} relative={relativeViewEnabled} />
        ))}
    </Fragment>
  );
}

type ToggleProps = { checked: boolean; onChange: (show: boolean) => void };

export function IndexRowsToggle({ checked, onChange }: ToggleProps) {
  const { t } = useTranslation();
  return (
    <label
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        marginBottom: '0.5rem',
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {t('group.indexRows.toggle')}
    </label>
  );
}

export default IndexBenchmarkRows;
