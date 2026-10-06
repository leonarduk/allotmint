import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getInstrumentValuation } from '../api';
import type { InstrumentPosition, InstrumentValuation } from '../types';
import { largeNumber, percent, quotedPrice } from '../lib/money';
import {
  navDateLabel,
  navUnreliability,
  signedPct,
  valuationCaveats,
} from '../lib/valuationCaveats';
import surfaceStyles from '../styles/surface.module.css';

type Row = { label: string; value: string; hint?: string; badge?: string };
type Section = { title: string; rows: Row[]; warn?: boolean };

const WARN_COLOR = '#b8860b';

const ratio = (v: number | null | undefined, digits = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits);
const pct = (v: number | null | undefined, digits = 1) =>
  v == null || !Number.isFinite(v) ? '—' : percent(v * 100, digits);

const NAV_SOURCE_KEY: Record<string, string> = {
  metadata: 'instrumentValuation.navSourceMetadata',
  reported_book_value: 'instrumentValuation.navSourceBookValue',
};

export function InstrumentValuationPanel({
  ticker,
  positions,
}: {
  ticker: string;
  positions: InstrumentPosition[];
}) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState<InstrumentValuation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      setProfile(null);
      try {
        setProfile(await getInstrumentValuation(ticker, controller.signal));
      } catch (err) {
        const e = err as {
          name?: string;
          status?: number;
          message?: string;
        } | null;
        if (e?.name === 'AbortError' || controller.signal.aborted) return;
        // 402 = not part of this deployment; the screener card already says so.
        if (e?.status !== 402)
          setError(
            t('instrumentValuation.loadError', {
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

  if (loading) return <div>{t('instrumentValuation.loading')}</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!profile) return null;

  const {
    valuation,
    nav,
    income,
    balance_sheet: bs,
    benchmark,
    risk,
  } = profile;
  const caveats = valuationCaveats(profile, positions);

  const sections: Section[] = [
    {
      title: t('instrumentValuation.multiples'),
      rows: [
        { label: t('instrumentValuation.peTrailing'), value: ratio(valuation.pe_ratio) },
        { label: t('instrumentValuation.peForward'), value: ratio(valuation.forward_pe) },
        { label: t('instrumentValuation.priceBook'), value: ratio(valuation.pb_ratio) },
        { label: t('instrumentValuation.evEbitda'), value: ratio(valuation.ev_ebitda) },
      ],
    },
    {
      title: t('instrumentValuation.income'),
      rows: [
        { label: t('instrumentValuation.dividendYield'), value: pct(income.dividend_yield, 2) },
        { label: t('instrumentValuation.payoutRatio'), value: pct(income.payout_ratio) },
        {
          label: t('instrumentValuation.dividendCover'),
          value:
            income.dividend_cover == null
              ? '—'
              : `${ratio(income.dividend_cover)}x`,
        },
      ],
    },
    {
      title: t('instrumentValuation.balanceSheet'),
      rows: [
        {
          label: t('instrumentValuation.netDebt'),
          value:
            bs.net_debt == null
              ? '—'
              : `${largeNumber(bs.net_debt)} ${bs.currency ?? ''}`.trim(),
        },
        {
          label: t('instrumentValuation.netGearing'),
          value: pct(bs.net_gearing),
          hint: t('instrumentValuation.netGearingHint'),
        },
        {
          label: t('instrumentValuation.debtEquity'),
          // Unlike net_gearing (a fraction), debt_to_equity is already a
          // percent as Yahoo reports it (45.4 = 45.4%), so it is not scaled.
          value:
            bs.debt_to_equity == null ? '—' : percent(bs.debt_to_equity, 1),
        },
      ],
    },
    {
      title: t('instrumentValuation.risk'),
      rows: [
        { label: t('instrumentValuation.volatility1y'), value: pct(risk.volatility_1y) },
        {
          label: t('instrumentValuation.beta', {
            ticker: benchmark.ticker,
          }),
          value: ratio(risk.beta_3y),
          hint:
            risk.beta_provider != null
              ? t('instrumentValuation.providerBeta', {
                  value: ratio(risk.beta_provider),
                })
              : undefined,
        },
        {
          label: t('instrumentValuation.maxDrawdown'),
          value: pct(risk.max_drawdown),
          hint:
            risk.max_drawdown_peak && risk.max_drawdown_trough
              ? `${risk.max_drawdown_peak} → ${risk.max_drawdown_trough}`
              : undefined,
        },
        {
          label: t('instrumentValuation.history'),
          value:
            risk.history_years == null ? '—' : t('instrumentValuation.years', { years: risk.history_years }),
          hint: risk.history_start
            ? `${risk.history_start} → ${risk.history_end}`
            : undefined,
        },
      ],
    },
  ];
  if (nav.nav_per_share != null) {
    // Trust NAVs move daily: a stale or undated NAV makes the premium/discount
    // unreliable, so say so on the figure itself, not only in the caveats.
    const unreliable = navUnreliability(nav);
    sections.unshift({
      title: t('instrumentValuation.nav'),
      warn: unreliable != null,
      rows: [
        {
          label: t('instrumentValuation.navPerShare'),
          value: quotedPrice(nav.nav_per_share, nav.currency ?? ''),
          hint: nav.source
            ? NAV_SOURCE_KEY[nav.source]
            ? t(NAV_SOURCE_KEY[nav.source])
            : nav.source
            : undefined,
        },
        {
          label: t('instrumentValuation.navLastUpdated'),
          value: navDateLabel(nav),
          hint:
            nav.max_age_days != null
              ? t('instrumentValuation.staleAfter', {
                  days: nav.max_age_days,
                })
              : undefined,
        },
        {
          label: t('instrumentValuation.premiumDiscount'),
          value: signedPct(nav.premium_discount),
          badge: unreliable?.badge,
          hint: unreliable?.reason,
        },
      ],
    });
  }

  return (
    <section aria-label={t('instrumentValuation.ariaValuation')} style={{ marginBottom: '1.5rem' }}>
      <p style={{ margin: '0 0 0.75rem' }}>
        {t('instrumentValuation.benchmark')} <strong>{benchmark.name ?? benchmark.ticker}</strong> (
        {benchmark.ticker}
        {benchmark.source === 'exchange_default'
          ? t('instrumentValuation.exchangeDefault')
          : ''}
        )
      </p>
      {caveats.length > 0 && (
        <div
          role="alert"
          aria-label={t('instrumentValuation.dataQuality')}
          className={surfaceStyles.surfaceCard}
          style={{ borderLeft: '4px solid #d97706', marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>
            {t('instrumentValuation.dataQuality')}
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
        }}
      >
        {sections.map((section) => (
          <div
            key={section.title}
            className={surfaceStyles.surfaceCard}
            style={
              section.warn
                ? { borderLeft: `4px solid ${WARN_COLOR}` }
                : undefined
            }
          >
            <h3 className={surfaceStyles.surfaceCardTitle}>{section.title}</h3>
            <table
              aria-label={section.title}
              style={{ width: '100%', borderCollapse: 'collapse' }}
            >
              <tbody>
                {section.rows.map((row) => (
                  <tr key={row.label} title={row.hint}>
                    <th
                      scope="row"
                      className={surfaceStyles.surfaceMuted}
                      style={{
                        textAlign: 'left',
                        padding: '0.35rem 0',
                        fontWeight: 500,
                      }}
                    >
                      {row.label}
                      {row.hint && (
                        <div style={{ fontSize: '0.75rem', fontWeight: 400 }}>
                          {row.hint}
                        </div>
                      )}
                    </th>
                    <td
                      style={{
                        textAlign: 'right',
                        padding: '0.35rem 0',
                        fontWeight: 600,
                      }}
                    >
                      {row.value}
                      {row.badge && (
                        <span
                          style={{
                            display: 'inline-block',
                            marginLeft: '0.5rem',
                            padding: '0.1rem 0.5rem',
                            borderRadius: '999px',
                            fontSize: '0.7rem',
                            backgroundColor: WARN_COLOR,
                            color: '#fff',
                            verticalAlign: 'middle',
                          }}
                        >
                          {row.badge}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </section>
  );
}
