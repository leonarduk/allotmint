import { useEffect, useState } from 'react';
import { getInstrumentValuation } from '../api';
import type { InstrumentPosition, InstrumentValuation } from '../types';
import { largeNumber, percent, quotedPrice } from '../lib/money';
import { signedPct, valuationCaveats } from '../lib/valuationCaveats';
import surfaceStyles from '../styles/surface.module.css';

type Row = { label: string; value: string; hint?: string };

const ratio = (v: number | null | undefined, digits = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits);
const pct = (v: number | null | undefined, digits = 1) =>
  v == null || !Number.isFinite(v) ? '—' : percent(v * 100, digits);

const NAV_SOURCE_LABEL: Record<string, string> = {
  metadata: 'recorded NAV',
  reported_book_value: 'last reported net assets per share',
};

export function InstrumentValuationPanel({
  ticker,
  positions,
}: {
  ticker: string;
  positions: InstrumentPosition[];
}) {
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
          setError(`Unable to load valuation: ${e?.message ?? String(err)}`);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [ticker]);

  if (loading) return <div>Loading valuation...</div>;
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

  const sections: { title: string; rows: Row[] }[] = [
    {
      title: 'Valuation multiples',
      rows: [
        { label: 'P/E (trailing)', value: ratio(valuation.pe_ratio) },
        { label: 'P/E (forward)', value: ratio(valuation.forward_pe) },
        { label: 'Price/Book', value: ratio(valuation.pb_ratio) },
        { label: 'EV/EBITDA', value: ratio(valuation.ev_ebitda) },
      ],
    },
    {
      title: 'Income',
      rows: [
        { label: 'Dividend yield', value: pct(income.dividend_yield, 2) },
        { label: 'Payout ratio', value: pct(income.payout_ratio) },
        {
          label: 'Dividend cover',
          value:
            income.dividend_cover == null
              ? '—'
              : `${ratio(income.dividend_cover)}x`,
        },
      ],
    },
    {
      title: 'Balance sheet',
      rows: [
        {
          label: 'Net debt',
          value:
            bs.net_debt == null
              ? '—'
              : `${largeNumber(bs.net_debt)} ${bs.currency ?? ''}`.trim(),
        },
        {
          label: 'Net gearing',
          value: pct(bs.net_gearing),
          hint: 'Net debt / net assets',
        },
        {
          label: 'Debt/Equity',
          value:
            bs.debt_to_equity == null ? '—' : percent(bs.debt_to_equity, 1),
        },
      ],
    },
    {
      title: 'Risk',
      rows: [
        { label: 'Volatility (1y)', value: pct(risk.volatility_1y) },
        {
          label: `Beta vs ${benchmark.ticker} (3y weekly)`,
          value: ratio(risk.beta_3y),
          hint:
            risk.beta_provider != null
              ? `Provider beta: ${ratio(risk.beta_provider)}`
              : undefined,
        },
        {
          label: 'Max drawdown',
          value: pct(risk.max_drawdown),
          hint:
            risk.max_drawdown_peak && risk.max_drawdown_trough
              ? `${risk.max_drawdown_peak} → ${risk.max_drawdown_trough}`
              : undefined,
        },
        {
          label: 'History',
          value:
            risk.history_years == null ? '—' : `${risk.history_years} years`,
          hint: risk.history_start
            ? `${risk.history_start} → ${risk.history_end}`
            : undefined,
        },
      ],
    },
  ];
  if (nav.nav_per_share != null) {
    sections.unshift({
      title: 'NAV',
      rows: [
        {
          label: 'NAV per share',
          value: quotedPrice(nav.nav_per_share, nav.currency ?? ''),
          hint: nav.source
            ? (NAV_SOURCE_LABEL[nav.source] ?? nav.source)
            : undefined,
        },
        { label: 'NAV date', value: nav.as_of ?? 'unknown' },
        { label: 'Premium/discount', value: signedPct(nav.premium_discount) },
      ],
    });
  }

  return (
    <section aria-label="Valuation" style={{ marginBottom: '1.5rem' }}>
      <p style={{ margin: '0 0 0.75rem' }}>
        Benchmark: <strong>{benchmark.name ?? benchmark.ticker}</strong> (
        {benchmark.ticker}
        {benchmark.source === 'exchange_default'
          ? ', default for the listing exchange'
          : ''}
        )
      </p>
      {caveats.length > 0 && (
        <div
          role="alert"
          aria-label="Data quality"
          className={surfaceStyles.surfaceCard}
          style={{ borderLeft: '4px solid #d97706', marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>Data quality</h3>
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
          <div key={section.title} className={surfaceStyles.surfaceCard}>
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
