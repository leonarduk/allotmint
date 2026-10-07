import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getDividends,
  getGroupPortfolio,
  getOwners,
  getPortfolio,
} from '../api';
import type { OwnerSummary, Transaction } from '../types';
import { useFetch } from '../hooks/useFetch';
import { useReportingCurrency } from '../hooks/useReportingCurrency';
import {
  holdingsFromAccounts,
  summariseDividends,
  type CurrencyAmounts,
  type DividendPeriod,
} from '../lib/dividends';
import { DEFAULT_GROUP_SLUG } from '../utils/groups';
import { sanitizeOwners } from '../utils/owners';
import tableStyles from '../styles/table.module.css';

const PERIODS: DividendPeriod[] = ['taxYear', 'year', 'month'];

export default function Dividends() {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState('');
  const [period, setPeriod] = useState<DividendPeriod>('taxYear');

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]));
  }, []);

  const fetchDividends = useCallback(
    () => getDividends(owner ? { owner } : undefined),
    [owner]
  );
  // Held tickers let the page list holdings that have never paid, so "no
  // history" is shown as such rather than as a zero amount.
  const fetchHoldings = useCallback(
    async () =>
      holdingsFromAccounts(
        (owner
          ? await getPortfolio(owner)
          : await getGroupPortfolio(DEFAULT_GROUP_SLUG)
        ).accounts
      ),
    [owner]
  );
  const dividends = useFetch<Transaction[]>(fetchDividends, [fetchDividends]);
  const holdings = useFetch(fetchHoldings, [fetchHoldings]);

  const summary = useMemo(
    () =>
      summariseDividends(dividends.data ?? [], {
        period,
        holdings: holdings.data ?? undefined,
      }),
    [dividends.data, holdings.data, period]
  );

  // `paidIn` holds the currencies with real history: a window with no
  // payments then reads as a true zero, while no history at all reads "—".
  const formatAmounts = (
    amounts: CurrencyAmounts,
    paidIn: CurrencyAmounts = amounts
  ) => {
    const entries = Object.keys(amounts).length
      ? Object.entries(amounts)
      : Object.keys(paidIn).map((currency): [string, number] => [currency, 0]);
    if (!entries.length) return t('dividends.none');
    return entries
      .map(([currency, amount]) => reporting.format(amount, currency))
      .join(' + ');
  };

  return (
    <div className="container mx-auto p-4">
      <h2>{t('dividends.title')}</h2>
      <p>{t('dividends.description')}</p>

      <div
        style={{
          display: 'flex',
          gap: '1rem',
          flexWrap: 'wrap',
          margin: '1rem 0',
        }}
      >
        <label>
          {t('dividends.owner')}{' '}
          <select value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">{t('dividends.allOwners')}</option>
            {owners.map((o) => (
              <option key={o.owner} value={o.owner}>
                {o.full_name || o.owner}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('dividends.period')}{' '}
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as DividendPeriod)}
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {t(`dividends.periods.${p}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {dividends.error && (
        <p role="alert" style={{ color: 'red' }}>
          {dividends.error.message}
        </p>
      )}
      {dividends.loading ? (
        <p>{t('common.loading')}</p>
      ) : (
        <>
          <dl style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
            <div>
              <dt>{t('dividends.trailing12m')}</dt>
              <dd
                data-testid="dividends-trailing-12m"
                style={{ fontSize: '1.5rem', margin: 0 }}
              >
                {formatAmounts(summary.trailing12m, summary.total)}
              </dd>
            </div>
            <div>
              <dt>{t('dividends.allTime')}</dt>
              <dd
                data-testid="dividends-total"
                style={{ fontSize: '1.5rem', margin: 0 }}
              >
                {formatAmounts(summary.total)}
              </dd>
            </div>
          </dl>

          {summary.payments === 0 ? (
            <p>{t('dividends.empty')}</p>
          ) : (
            <>
              <h3 style={{ marginTop: '1.5rem' }}>{t('dividends.byPeriod')}</h3>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th className={tableStyles.cell}>
                      {t(`dividends.periods.${period}`)}
                    </th>
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t('dividends.payments')}
                    </th>
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t('dividends.received')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {summary.periods.map((row) => (
                    <tr key={row.period}>
                      <td className={tableStyles.cell}>
                        {row.period || t('dividends.undated')}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {row.payments}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {formatAmounts(row.amounts)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h3 style={{ marginTop: '1.5rem' }}>{t('dividends.byHolding')}</h3>
          {holdings.error && <p>{t('dividends.holdingsUnavailable')}</p>}
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>{t('dividends.holding')}</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t('dividends.payments')}
                </th>
                <th className={tableStyles.cell}>{t('dividends.lastPaid')}</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t('dividends.trailing12m')}
                </th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t('dividends.allTime')}
                </th>
              </tr>
            </thead>
            <tbody>
              {summary.holdings.map((row) => (
                <tr key={row.ticker ?? '__unattributed'}>
                  <td className={tableStyles.cell}>
                    {row.ticker ? (
                      <>
                        {row.ticker}
                        {row.name && (
                          <span style={{ opacity: 0.7 }}> — {row.name}</span>
                        )}
                      </>
                    ) : (
                      <span title={t('dividends.unattributedHelp')}>
                        {t('dividends.unattributed')}
                      </span>
                    )}
                  </td>
                  {row.payments === 0 ? (
                    <td className={tableStyles.cell} colSpan={4}>
                      <em>{t('dividends.noHistory')}</em>
                    </td>
                  ) : (
                    <>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {row.payments}
                      </td>
                      <td className={tableStyles.cell}>{row.lastPaid ?? ''}</td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {formatAmounts(row.trailing12m, row.total)}
                      </td>
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                      >
                        {formatAmounts(row.total)}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
