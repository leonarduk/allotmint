import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getInstrumentCreditRisk } from '../api';
import type { CreditRiskBand, InstrumentCreditRisk } from '../types';
import { largeNumber, percent } from '../lib/money';
import surfaceStyles from '../styles/surface.module.css';

const BAND_COLOR: Record<CreditRiskBand, string> = {
  high: '#b91c1c',
  watch: '#b8860b',
  low: '#15803d',
  unknown: '#6b7280',
};

// Signal name -> i18n label key, in display order.
const SIGNAL_LABELS: [string, string][] = [
  ['altman_z', 'instrumentCreditRisk.altmanZ'],
  ['interest_coverage', 'instrumentCreditRisk.interestCover'],
  ['net_debt_to_ebitda', 'instrumentCreditRisk.netDebtToEbitda'],
  ['current_ratio', 'instrumentCreditRisk.currentRatio'],
  ['fcf', 'instrumentCreditRisk.fcf'],
  ['from_52w_high', 'instrumentCreditRisk.from52wHigh'],
];

// Market spread series -> i18n label key.
const SPREAD_LABELS: Record<string, string> = {
  us_high_yield: 'instrumentCreditRisk.usHighYield',
  euro_high_yield: 'instrumentCreditRisk.euroHighYield',
  baa_10y: 'instrumentCreditRisk.baa10y',
};

const ratio = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(2);

function signalValue(
  name: string,
  value: number | null,
  currency: string | null
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (name === 'fcf') return `${largeNumber(value)} ${currency ?? ''}`.trim();
  if (name === 'from_52w_high') return percent(value * 100, 0);
  if (name === 'interest_coverage' || name === 'net_debt_to_ebitda')
    return `${ratio(value)}x`;
  return ratio(value);
}

function useCreditRisk(ticker: string) {
  const { t } = useTranslation();
  const [data, setData] = useState<InstrumentCreditRisk | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        setData(await getInstrumentCreditRisk(ticker, controller.signal));
      } catch (err) {
        const e = err as {
          name?: string;
          status?: number;
          message?: string;
        } | null;
        if (e?.name === 'AbortError' || controller.signal.aborted) return;
        // 402 = not part of this deployment: show nothing rather than an error.
        if (e?.status !== 402)
          setError(
            t('instrumentCreditRisk.loadError', {
              message: e?.message ?? String(err),
            })
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [ticker, t]);

  return { data, loading, error };
}

function MarketContext({
  context,
}: {
  context: InstrumentCreditRisk['market_context'];
}) {
  const { t } = useTranslation();
  if (!context?.available || !context.series) return null;
  const readings = Object.entries(context.series).filter(
    ([, r]) => r.value != null
  );
  if (readings.length === 0) return null;
  return (
    <p
      className={surfaceStyles.surfaceMuted}
      style={{ margin: '0.75rem 0 0', fontSize: '0.85rem' }}
    >
      {t('instrumentCreditRisk.marketContext')}{' '}
      {readings
        .map(([name, r]) =>
          t('instrumentCreditRisk.spreadReading', {
            label: SPREAD_LABELS[name] ? t(SPREAD_LABELS[name]) : name,
            value: ratio(r.value),
            percentile: r.percentile == null ? '—' : Math.round(r.percentile),
          })
        )
        .join('; ')}
    </p>
  );
}

export function InstrumentCreditRiskPanel({ ticker }: { ticker: string }) {
  const { t } = useTranslation();
  const { data, loading, error } = useCreditRisk(ticker);

  if (loading) return <div>{t('instrumentCreditRisk.loading')}</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!data) return null;

  const { result } = data;
  const color = BAND_COLOR[result.band] ?? BAND_COLOR.unknown;
  // The route passes the pro row through as-is, so do not trust every list to be present.
  const notes = [...(result.reasons ?? []), ...(result.mitigations ?? [])];
  const dataGaps = result.data_gaps ?? [];
  const signals = result.signals ?? {};

  return (
    <section
      aria-label={t('instrumentCreditRisk.title')}
      className={surfaceStyles.surfaceCard}
      style={{ borderLeft: `4px solid ${color}`, marginBottom: '1.5rem' }}
    >
      <h3 className={surfaceStyles.surfaceCardTitle}>
        {t('instrumentCreditRisk.title')}{' '}
        <span
          data-testid="credit-risk-band"
          style={{
            display: 'inline-block',
            marginLeft: '0.5rem',
            padding: '0.1rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.75rem',
            backgroundColor: color,
            color: '#fff',
            verticalAlign: 'middle',
          }}
        >
          {t(`instrumentCreditRisk.band.${result.band}`)}
        </span>
      </h3>
      {notes.length > 0 && (
        <ul style={{ margin: '0 0 0.75rem', paddingLeft: '1.25rem' }}>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <table
        aria-label={t('instrumentCreditRisk.signals')}
        style={{ width: '100%', borderCollapse: 'collapse' }}
      >
        <tbody>
          {SIGNAL_LABELS.filter(([name]) => signals[name]).map(
            ([name, labelKey]) => (
              <tr key={name}>
                <th
                  scope="row"
                  className={surfaceStyles.surfaceMuted}
                  style={{
                    textAlign: 'left',
                    padding: '0.3rem 0',
                    fontWeight: 500,
                  }}
                >
                  {t(labelKey)}
                </th>
                <td
                  style={{
                    textAlign: 'right',
                    padding: '0.3rem 0',
                    fontWeight: 600,
                  }}
                >
                  {signalValue(
                    name,
                    signals[name].value,
                    result.financial_currency
                  )}
                </td>
              </tr>
            )
          )}
        </tbody>
      </table>
      <p
        className={surfaceStyles.surfaceMuted}
        style={{ margin: '0.75rem 0 0', fontSize: '0.85rem' }}
      >
        {result.statements_as_of
          ? t('instrumentCreditRisk.accountsAsOf', {
              date: result.statements_as_of,
            })
          : t('instrumentCreditRisk.noAccountsDate')}
        {dataGaps.length > 0 &&
          ` · ${t('instrumentCreditRisk.dataGaps', { fields: dataGaps.join(', ') })}`}
      </p>
      <MarketContext context={data.market_context} />
      <p
        className={surfaceStyles.surfaceMuted}
        style={{ margin: '0.5rem 0 0', fontSize: '0.8rem' }}
      >
        {t('instrumentCreditRisk.disclaimer')}
      </p>
    </section>
  );
}
