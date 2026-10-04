import { useEffect, useState } from 'react';
import { getInstrumentTechnicals } from '../api';
import type { InstrumentTechnicals } from '../types';
import { percent } from '../lib/money';
import { signedPct } from '../lib/valuationCaveats';
import surfaceStyles from '../styles/surface.module.css';

type Row = { label: string; value: string; hint?: string };

const num = (v: number | null | undefined, digits = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits);
const pct = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v) ? '—' : percent(v * 100, digits);
const label = (v: string | null | undefined) =>
  v ? v.charAt(0).toUpperCase() + v.slice(1) : '—';
const withDate = (v: string | null, date: string | null) =>
  v ? `${label(v)}${date ? ` (${date})` : ''}` : '—';

const vsHint = (v: number | null) =>
  v == null ? undefined : `Price ${signedPct(v)} vs average`;

const RETURN_LABELS: Record<string, string> = {
  '1m': '1 month',
  '3m': '3 months',
  '6m': '6 months',
  '1y': '12 months',
};

export function InstrumentTechnicalsPanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<InstrumentTechnicals | null>(null);
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
        setData(await getInstrumentTechnicals(ticker, controller.signal));
      } catch (err) {
        const e = err as {
          name?: string;
          status?: number;
          message?: string;
        } | null;
        if (e?.name === 'AbortError' || controller.signal.aborted) return;
        setError(
          e?.status === 402
            ? 'Technical analysis is not available in this deployment.'
            : `Unable to load technicals: ${e?.message ?? String(err)}`
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [ticker]);

  if (loading) return <div>Loading technicals...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!data) return null;

  const {
    moving_averages: ma,
    rsi,
    macd,
    bollinger: bb,
    range_52w: range,
    returns,
    relative_strength: rs,
    data_quality: quality,
  } = data;
  const units = data.price_currency ? ` ${data.price_currency}` : '';
  const level = (v: number | null) => (v == null ? '—' : `${num(v)}${units}`);
  const benchmarkName = rs.benchmark.name ?? rs.benchmark.ticker;

  const sections: { title: string; rows: Row[] }[] = [
    {
      title: 'Trend',
      rows: [
        {
          label: 'Trend',
          value: label(ma.trend),
          hint: 'Price vs 50- and 200-day averages',
        },
        {
          label: '20-day average',
          value: level(ma.sma_20),
          hint: vsHint(ma.vs_sma_20),
        },
        {
          label: '50-day average',
          value: level(ma.sma_50),
          hint: vsHint(ma.vs_sma_50),
        },
        {
          label: '200-day average',
          value: level(ma.sma_200),
          hint: vsHint(ma.vs_sma_200),
        },
        {
          label: '50/200 cross',
          value: label(ma.cross_state),
          hint: ma.last_cross_date
            ? `Last ${ma.last_cross} cross ${ma.last_cross_date}`
            : undefined,
        },
      ],
    },
    {
      title: 'Momentum',
      rows: [
        {
          label: `RSI (${rsi.period})`,
          value: num(rsi.value, 0),
          hint: label(rsi.zone),
        },
        {
          label: 'MACD (12/26/9)',
          value: num(macd.macd),
          hint: `Signal ${num(macd.signal)}`,
        },
        { label: 'MACD histogram', value: num(macd.histogram) },
        {
          label: 'Last MACD crossover',
          value: withDate(macd.last_crossover, macd.last_crossover_date),
        },
      ],
    },
    {
      title: 'Range',
      rows: [
        {
          label: '52-week high',
          value: level(range.high),
          hint: range.high_date ?? undefined,
        },
        {
          label: '52-week low',
          value: level(range.low),
          hint: range.low_date ?? undefined,
        },
        { label: 'From 52-week high', value: signedPct(range.from_high) },
        {
          label: 'Position in range',
          value: pct(range.position),
          hint: '0% = at the low, 100% = at the high',
        },
        {
          label: 'Bollinger %B (20, 2σ)',
          value: pct(bb.percent_b),
          hint:
            bb.lower != null
              ? `Bands ${num(bb.lower)} – ${num(bb.upper)}`
              : undefined,
        },
      ],
    },
    {
      title: 'Returns',
      rows: [
        ...Object.entries(RETURN_LABELS).map(([key, text]) => ({
          label: text,
          value: signedPct(returns[key] ?? null),
        })),
        {
          label: `vs ${rs.benchmark.ticker} (3m)`,
          value: signedPct(rs.excess_3m),
          hint: benchmarkName,
        },
        {
          label: `vs ${rs.benchmark.ticker} (12m)`,
          value: signedPct(rs.excess_1y),
          hint: benchmarkName,
        },
      ],
    },
  ];

  return (
    <section aria-label="Technicals" style={{ marginBottom: '1.5rem' }}>
      <p style={{ margin: '0 0 0.75rem' }}>
        From {quality.data_points} daily closes
        {data.as_of ? ` to ${data.as_of}` : ''}. These describe the price chart;
        they are not buy or sell recommendations.
      </p>
      {quality.warnings.length > 0 && (
        <div
          role="alert"
          aria-label="Data quality"
          className={surfaceStyles.surfaceCard}
          style={{ borderLeft: '4px solid #d97706', marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>Data quality</h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {quality.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {data.signals.length > 0 && (
        <div
          aria-label="Signals"
          className={surfaceStyles.surfaceCard}
          style={{ marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>
            What the chart shows
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {data.signals.map((s) => (
              <li key={s}>{s}</li>
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
