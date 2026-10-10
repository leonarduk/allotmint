// Risk/return columns, controls and status line for the Screener
// (allotmint#10607). Figures come from GET /screener/risk-return.
import { useTranslation } from 'react-i18next';
import InfoTip from './InfoTip';
import type { RiskReturnState } from '../hooks/useScreenerRiskReturn';
import {
  RISK_PERIODS,
  type RiskCurrency,
  type RiskFilters,
  type RiskPeriod,
  type ScreenerRow,
  type SharpeScope,
} from '../lib/screenerRiskReturn';

const cell = { padding: '4px 6px' } as const;
const right = { ...cell, textAlign: 'right', cursor: 'pointer' } as const;

const NOT_A_FORECAST = ' Past figures are not a forecast.';

const RISK_TIPS = {
  sharpe: {
    defaultText:
      'Annualised return above the risk-free rate (mean Bank Rate over the window) divided by annualised volatility of weekly returns.' +
      NOT_A_FORECAST,
    anchor: 'screener-risk-return',
  },
  minSharpe: {
    defaultText:
      'The lowest of the 3, 5 and 10-year Sharpe ratios — blank unless all three exist. A high minimum means consistently good risk-adjusted returns.' +
      NOT_A_FORECAST,
    anchor: 'screener-risk-return',
  },
  return: {
    defaultText:
      'Annualised return over the selected period, in the selected currency.' +
      NOT_A_FORECAST,
    anchor: 'screener-risk-return',
  },
  volatility: {
    defaultText:
      'Annualised standard deviation of weekly returns over the selected period.',
    anchor: 'screener-risk-return',
  },
  worstFall: {
    defaultText: 'The largest peak-to-trough fall over the selected period.',
    anchor: 'max-drawdown',
  },
  basis: {
    defaultText:
      'Currency the figures are in, and whether returns include dividends (total), include them only for part of the history (partial), or are price only.',
    anchor: 'screener-risk-return',
  },
} as const;

type TipKey = keyof typeof RISK_TIPS;

function RiskTip({ tip, column }: { tip: TipKey; column: string }) {
  const { t } = useTranslation();
  const { defaultText, anchor } = RISK_TIPS[tip];
  return (
    <InfoTip
      label={t('screener.tips.infoLabel', 'What does {{column}} mean?', {
        column,
      })}
      to={`/metrics-explained#${anchor}`}
    >
      {t(`screener.tips.risk.${tip}`, defaultText)}
    </InfoTip>
  );
}

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`;
const ratio = (v: number | null | undefined) =>
  v == null ? '—' : v.toFixed(2);

export function RiskReturnHeaders({
  period,
  onSort,
}: {
  period: RiskPeriod;
  onSort: (key: keyof ScreenerRow) => void;
}) {
  const { t } = useTranslation();
  const sharpeHeader = (years: RiskPeriod) => {
    const label = t('screener.risk.col.sharpe', { years });
    return (
      <th key={years} style={right} onClick={() => onSort(`sharpe_${years}y`)}>
        {label}
        <RiskTip tip="sharpe" column={label} />
      </th>
    );
  };
  const header = (key: keyof ScreenerRow, label: string, tip: TipKey) => (
    <th style={right} onClick={() => onSort(key)}>
      {label}
      <RiskTip tip={tip} column={label} />
    </th>
  );
  return (
    <>
      {RISK_PERIODS.map(sharpeHeader)}
      {header('min_sharpe', t('screener.risk.col.minSharpe'), 'minSharpe')}
      {header(
        'risk_return',
        t('screener.risk.col.return', { years: period }),
        'return'
      )}
      {header(
        'risk_volatility',
        t('screener.risk.col.volatility', { years: period }),
        'volatility'
      )}
      {header(
        'risk_max_drawdown',
        t('screener.risk.col.worstFall', { years: period }),
        'worstFall'
      )}
      {header('risk_currency', t('screener.risk.col.basis'), 'basis')}
    </>
  );
}

export function RiskReturnCells({
  row,
  loading,
  period,
}: {
  row: ScreenerRow;
  loading: boolean;
  period: RiskPeriod;
}) {
  const { t } = useTranslation();
  if (loading) {
    const pending = t('screener.risk.pending');
    return (
      <>
        {Array.from({ length: 8 }, (_, i) => (
          <td key={i} style={right} title={pending}>
            …
          </td>
        ))}
      </>
    );
  }
  const blankReason =
    row.risk_status === 'missing'
      ? t('screener.risk.noHistory')
      : row.risk_status === 'short'
        ? t('screener.risk.shortHistory', { years: period })
        : row.risk_status === 'absent'
          ? t('screener.risk.notReturned')
          : undefined;
  const basis = row.risk_basis
    ? t(`screener.risk.basis.${row.risk_basis}`)
    : null;
  return (
    <>
      <td style={right} title={blankReason}>
        {ratio(row.sharpe_3y)}
      </td>
      <td style={right} title={blankReason}>
        {ratio(row.sharpe_5y)}
      </td>
      <td style={right} title={blankReason}>
        {ratio(row.sharpe_10y)}
      </td>
      <td style={right} title={blankReason}>
        {ratio(row.min_sharpe)}
      </td>
      <td style={right} title={blankReason}>
        {pct(row.risk_return)}
      </td>
      <td style={right} title={blankReason}>
        {pct(row.risk_volatility)}
      </td>
      <td style={right} title={blankReason}>
        {pct(row.risk_max_drawdown)}
      </td>
      <td style={{ ...cell, whiteSpace: 'nowrap' }} title={blankReason}>
        {row.risk_currency && basis ? `${row.risk_currency} · ${basis}` : '—'}
      </td>
    </>
  );
}

export interface RiskControlsProps {
  filters: RiskFilters;
  onFilters: (next: RiskFilters) => void;
  currency: RiskCurrency;
  onCurrency: (next: RiskCurrency) => void;
  period: RiskPeriod;
  onPeriod: (next: RiskPeriod) => void;
}

export function RiskReturnControls(props: RiskControlsProps) {
  const { filters, onFilters, currency, onCurrency, period, onPeriod } = props;
  const { t } = useTranslation();
  const periodLabel = (years: RiskPeriod) =>
    t('screener.risk.periodOption', { years });
  return (
    <fieldset className="mb-4 flex flex-wrap items-center gap-2">
      <legend>{t('screener.risk.controlsLabel')}</legend>
      <label>
        {t('screener.risk.currency')}
        <select
          aria-label={t('screener.risk.currency')}
          value={currency}
          onChange={(e) => onCurrency(e.target.value as RiskCurrency)}
          className="ml-1 border px-2 py-1"
        >
          <option value="gbp">{t('screener.risk.currencyGbp')}</option>
          <option value="local">{t('screener.risk.currencyLocal')}</option>
        </select>
      </label>
      <label>
        {t('screener.risk.period')}
        <select
          aria-label={t('screener.risk.period')}
          value={period}
          onChange={(e) => onPeriod(e.target.value as RiskPeriod)}
          className="ml-1 border px-2 py-1"
        >
          {RISK_PERIODS.map((p) => (
            <option key={p} value={p}>
              {periodLabel(p)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('screener.risk.minSharpe')}
        <input
          aria-label={t('screener.risk.minSharpe')}
          type="number"
          step="any"
          value={filters.minSharpe}
          onChange={(e) => onFilters({ ...filters, minSharpe: e.target.value })}
          style={{ marginLeft: '0.25rem', width: '5rem' }}
        />
      </label>
      <label>
        {t('screener.risk.sharpeScope')}
        <select
          aria-label={t('screener.risk.sharpeScope')}
          value={filters.sharpeScope}
          onChange={(e) =>
            onFilters({
              ...filters,
              sharpeScope: e.target.value as SharpeScope,
            })
          }
          className="ml-1 border px-2 py-1"
        >
          <option value="all">{t('screener.risk.scopeAll')}</option>
          {RISK_PERIODS.map((p) => (
            <option key={p} value={p}>
              {periodLabel(p)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('screener.risk.maxDrawdown')}
        <input
          aria-label={t('screener.risk.maxDrawdown')}
          type="number"
          step="any"
          min="0"
          value={filters.maxDrawdown}
          placeholder={t('screener.fractionHint', '0.10 = 10%')}
          onChange={(e) =>
            onFilters({ ...filters, maxDrawdown: e.target.value })
          }
          style={{ marginLeft: '0.25rem', width: '6rem' }}
        />
      </label>
    </fieldset>
  );
}

function formatRates(riskFree: Record<string, number | null>): string {
  return RISK_PERIODS.filter((p) => riskFree[p] != null)
    .map((p) => `${p}y ${pct(riskFree[p])}`)
    .join(', ');
}

/** One status line: loading, error, or as-of date, risk-free rates and gaps. */
export function RiskReturnSummary({
  state,
  currency,
  hiddenByFilters,
}: {
  state: RiskReturnState;
  currency: RiskCurrency;
  hiddenByFilters: number;
}) {
  const { t } = useTranslation();
  if (state.status === 'loading')
    return <p role="status">{t('screener.risk.loading')}</p>;
  if (state.status === 'error') {
    return (
      <p role="status">
        {t('screener.risk.error', { error: state.error ?? '' })}
      </p>
    );
  }
  if (state.status !== 'ready' || !state.data) return null;
  const { data } = state;
  return (
    <div role="status" className="mb-2 text-sm">
      <p title={data.method}>
        {t('screener.risk.summary', {
          date: data.as_of ?? '—',
          currency:
            currency === 'gbp'
              ? t('screener.risk.currencyGbp')
              : t('screener.risk.currencyLocal'),
          rates: formatRates(data.risk_free ?? {}) || '—',
        })}
      </p>
      {data.missing.length > 0 && (
        <p>{t('screener.risk.missing', { count: data.missing.length })}</p>
      )}
      {hiddenByFilters > 0 && (
        <p>{t('screener.risk.filteredOut', { count: hiddenByFilters })}</p>
      )}
    </div>
  );
}
