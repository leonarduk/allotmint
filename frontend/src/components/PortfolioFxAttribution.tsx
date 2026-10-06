import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { getFxAttribution } from '../api';
import { money, percent } from '../lib/money';
import type {
  FxAttribution,
  FxAttributionComponents,
  FxAttributionCurrency,
} from '../types';

// Every attribution amount is GBP (the ledger's currency); money() only
// labels it, it does not convert.
const fmt = (v: number) => money(v, 'GBP');

type Props = {
  owner: string;
  /** The dashboard's window in days (0 is not sent: the caller maps "max" to a long window). */
  days: number;
  asOf?: string | null;
};

type Line = { key: keyof FxAttributionComponents; label: string };

function useLines(): Line[] {
  const { t } = useTranslation();
  return [
    { key: 'local_gbp', label: t('dashboard.fxAttribution.local') },
    { key: 'fx_gbp', label: t('dashboard.fxAttribution.fx') },
    { key: 'income_gbp', label: t('dashboard.fxAttribution.income') },
    { key: 'residual_gbp', label: t('dashboard.fxAttribution.other') },
    {
      key: 'unattributed_gbp',
      label: t('dashboard.fxAttribution.unattributed'),
    },
    { key: 'pnl_gbp', label: t('dashboard.fxAttribution.total') },
  ];
}

function PortfolioLine({ totals }: { totals: FxAttributionComponents }) {
  const lines = useLines().filter(
    (line) => line.key !== 'unattributed_gbp' || totals.unattributed_gbp !== 0
  );
  return (
    <div
      className="flex-wrap-row"
      style={{ gap: '1rem', marginBottom: '0.75rem' }}
    >
      {lines.map((line) => (
        <div key={line.key} data-testid={`fx-attribution-${line.key}`}>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>{line.label}</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>
            {fmt(totals[line.key])}
          </div>
        </div>
      ))}
    </div>
  );
}

function CurrencyTable({ rows }: { rows: FxAttributionCurrency[] }) {
  const { t } = useTranslation();
  const lines = useLines().filter(
    (line) =>
      line.key !== 'unattributed_gbp' ||
      rows.some((row) => row.unattributed_gbp !== 0)
  );
  return (
    <table
      data-testid="fx-attribution-by-currency"
      style={{ fontSize: '0.85rem' }}
    >
      <thead>
        <tr>
          <th style={{ textAlign: 'left', paddingRight: '1rem' }}>
            {t('dashboard.fxAttribution.currency')}
          </th>
          {lines.map((line) => (
            <th
              key={line.key}
              style={{ textAlign: 'right', paddingRight: '1rem' }}
            >
              {line.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.currency}>
            <td style={{ paddingRight: '1rem' }}>{row.currency}</td>
            {lines.map((line) => (
              <td
                key={line.key}
                style={{ textAlign: 'right', paddingRight: '1rem' }}
              >
                {line.key === 'fx_gbp' && !row.fx_applicable
                  ? t('dashboard.fxAttribution.notApplicable')
                  : fmt(row[line.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AttributionNotes({ data }: { data: FxAttribution }) {
  const { t, i18n } = useTranslation();
  const { coverage } = data;
  const unconverted = data.unconverted_holdings;
  return (
    <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.5rem' }}>
      <p data-testid="fx-attribution-coverage">
        {coverage.share === null
          ? t('dashboard.fxAttribution.coverageUnknown')
          : t('dashboard.fxAttribution.coverage', {
              share: percent(coverage.share * 100, 0, i18n.language),
              ledger: fmt(coverage.ledger_value_gbp),
              portfolio: fmt(coverage.portfolio_value_gbp),
            })}
      </p>
      {coverage.unreconciled_holdings.length > 0 && (
        <p>
          {t('dashboard.fxAttribution.unreconciled', {
            holdings: coverage.unreconciled_holdings.join(', '),
          })}
        </p>
      )}
      {unconverted.length > 0 && (
        <p
          data-testid="fx-attribution-unconverted"
          style={{ color: '#facc15' }}
        >
          {t('dashboard.fxAttribution.unconverted', {
            holdings: unconverted
              .map((h) => `${h.ticker} (${h.currency})`)
              .join(', '),
          })}
        </p>
      )}
      <p>{t('dashboard.fxAttribution.quoteCurrencyNote')}</p>
      {!data.cash_fx_modelled && (
        <p>{t('dashboard.fxAttribution.cashNotModelled')}</p>
      )}
    </div>
  );
}

/**
 * Where the portfolio's GBP P&L over the window came from: local price
 * moves, currency moves, income and trading/other, overall and per quote
 * currency (#9804).
 */
export function PortfolioFxAttribution({ owner, days, asOf }: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<FxAttribution | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(undefined);
    setFailed(false);
    getFxAttribution(owner, days, asOf ? { asOf } : {})
      .then((res) => {
        if (!cancelled) setData(res.fx_attribution);
      })
      .catch(() => {
        // Shown as unavailable below; the rest of the dashboard is unaffected.
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [owner, days, asOf]);

  let body;
  if (failed) body = <p>{t('dashboard.fxAttribution.unavailable')}</p>;
  else if (data === undefined) body = <p>{t('common.loading')}</p>;
  else if (data === null) body = <p>{t('dashboard.fxAttribution.noLedger')}</p>;
  else
    body = (
      <>
        <PortfolioLine totals={data.totals} />
        <h3 style={{ fontSize: '0.95rem', margin: '0.5rem 0' }}>
          {t('dashboard.fxAttribution.byCurrency')}
        </h3>
        <CurrencyTable rows={data.by_currency} />
        <AttributionNotes data={data} />
      </>
    );
  return (
    <section data-testid="fx-attribution" style={{ marginBottom: '1.5rem' }}>
      <h2>{t('dashboard.fxAttribution.title')}</h2>
      <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
        {t('dashboard.fxAttribution.description')}
      </p>
      {body}
    </section>
  );
}

export default PortfolioFxAttribution;
