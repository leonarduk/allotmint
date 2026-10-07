import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useInRouterContext } from 'react-router-dom';
import { getInstrumentTechnicals } from '../api';
import type { InstrumentTechnicals } from '../types';
import { percent } from '../lib/money';
import { signedPct } from '../lib/valuationCaveats';
import {
  TECHNICALS_GLOSSARY_ANCHOR,
  technicalsTerm,
  type TechnicalsTerm,
} from '../lib/technicalsGlossary';
import InfoTip from './InfoTip';
import surfaceStyles from '../styles/surface.module.css';

type Row = {
  label: string;
  value: string;
  hint?: string;
  /** Glossary term explained by the row's InfoTip. */
  term?: TechnicalsTerm;
};

const GLOSSARY_PATH = '/metrics-explained';

function TermTip({ term }: { term: TechnicalsTerm }) {
  const { t } = useTranslation();
  const entry = technicalsTerm(term);
  const glossaryKey = `metricsExplanation.sections.technicals.${entry.key}`;
  return (
    <InfoTip
      label={t('instrumentTechnicals.whatDoesMean', {
        title: t(`${glossaryKey}.title`),
      })}
      to={`${GLOSSARY_PATH}#${entry.id}`}
    >
      {t(`${glossaryKey}.short`)}
    </InfoTip>
  );
}

const CROSS_KEY: Record<string, string> = {
  golden: 'instrumentTechnicals.crossGolden',
  death: 'instrumentTechnicals.crossDeath',
};

const num = (v: number | null | undefined, digits = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits);
const pct = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v) ? '—' : percent(v * 100, digits);
const label = (v: string | null | undefined) =>
  v ? v.charAt(0).toUpperCase() + v.slice(1) : '—';
const withDate = (v: string | null, date: string | null) =>
  v ? `${label(v)}${date ? ` (${date})` : ''}` : '—';

const RETURN_KEYS: Record<string, string> = {
  '1m': 'instrumentTechnicals.return1m',
  '3m': 'instrumentTechnicals.return3m',
  '6m': 'instrumentTechnicals.return6m',
  '1y': 'instrumentTechnicals.return1y',
};

export function InstrumentTechnicalsPanel({ ticker }: { ticker: string }) {
  const { t } = useTranslation();
  const inRouterContext = useInRouterContext();
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
            ? t('instrumentTechnicals.unavailable')
            : t('instrumentTechnicals.loadError', {
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

  if (loading) return <div>{t('instrumentTechnicals.loading')}</div>;
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
  const vsHint = (v: number | null) =>
    v == null
      ? undefined
      : t('instrumentTechnicals.priceVsAverage', { value: signedPct(v) });
  const benchmarkTicker = rs.benchmark.ticker;
  const benchmarkName = rs.benchmark.name ?? benchmarkTicker ?? undefined;

  const sections: { title: string; term?: TechnicalsTerm; rows: Row[] }[] = [
    {
      title: t('instrumentTechnicals.trend'),
      rows: [
        {
          label: t('instrumentTechnicals.trend'),
          value: label(ma.trend),
          hint: t('instrumentTechnicals.trendHint'),
          term: 'trend',
        },
        {
          label: t('instrumentTechnicals.avg20'),
          value: level(ma.sma_20),
          hint: vsHint(ma.vs_sma_20),
          term: 'movingAverage',
        },
        {
          label: t('instrumentTechnicals.avg50'),
          value: level(ma.sma_50),
          hint: vsHint(ma.vs_sma_50),
          term: 'movingAverage',
        },
        {
          label: t('instrumentTechnicals.avg200'),
          value: level(ma.sma_200),
          hint: vsHint(ma.vs_sma_200),
          term: 'movingAverage',
        },
        {
          label: t('instrumentTechnicals.cross'),
          value: ma.cross_state
            ? (CROSS_KEY[ma.cross_state]
                ? t(CROSS_KEY[ma.cross_state])
                : label(ma.cross_state))
            : '—',
          term: 'cross',
          hint: ma.last_cross_date
            ? t('instrumentTechnicals.lastCross', {
                cross: ma.last_cross,
                date: ma.last_cross_date,
              })
            : undefined,
        },
      ],
    },
    {
      title: t('instrumentTechnicals.momentum'),
      rows: [
        {
          label: `RSI (${rsi.period})`,
          value: num(rsi.value, 0),
          hint: label(rsi.zone),
          term: 'rsi',
        },
        {
          label: 'MACD (12/26/9)',
          value: num(macd.macd),
          hint: t('instrumentTechnicals.signal', { value: num(macd.signal) }),
          term: 'macd',
        },
        { label: t('instrumentTechnicals.macdHistogram'), value: num(macd.histogram), term: 'macd' },
        {
          label: t('instrumentTechnicals.lastMacdCrossover'),
          value: withDate(macd.last_crossover, macd.last_crossover_date),
          term: 'macd',
        },
      ],
    },
    {
      title: t('instrumentTechnicals.range'),
      rows: [
        {
          label: t('instrumentTechnicals.high52'),
          value: level(range.high),
          hint: range.high_date ?? undefined,
          term: 'range',
        },
        {
          label: t('instrumentTechnicals.low52'),
          value: level(range.low),
          hint: range.low_date ?? undefined,
        },
        { label: t('instrumentTechnicals.fromHigh52'), value: signedPct(range.from_high) },
        {
          label: t('instrumentTechnicals.positionInRange'),
          value: pct(range.position),
          hint: t('instrumentTechnicals.positionHint'),
          term: 'range',
        },
        {
          label: t('instrumentTechnicals.bollinger'),
          value: pct(bb.percent_b),
          hint:
            bb.lower != null
              ? t('instrumentTechnicals.bands', {
                  lower: num(bb.lower),
                  upper: num(bb.upper),
                })
              : undefined,
          term: 'bollinger',
        },
      ],
    },
    {
      title: t('instrumentTechnicals.returns'),
      term: 'returns',
      rows: [
        ...Object.entries(RETURN_KEYS).map(([key, text]) => ({
          label: t(text),
          value: signedPct(returns[key] ?? null),
        })),
        // No comparable benchmark (bond, cash, commodity fund): there is
        // nothing to measure relative strength against, so omit the rows.
        ...(benchmarkTicker == null
          ? []
          : [
              {
                label: t('instrumentTechnicals.vs3m', {
                  ticker: benchmarkTicker,
                }),
                value: signedPct(rs.excess_3m),
                hint: benchmarkName,
                term: 'relativeStrength' as const,
              },
              {
                label: t('instrumentTechnicals.vs12m', {
                  ticker: benchmarkTicker,
                }),
                value: signedPct(rs.excess_1y),
                hint: benchmarkName,
                term: 'relativeStrength' as const,
              },
            ]),
      ],
    },
  ];

  return (
    <section aria-label={t('instrumentTechnicals.ariaTechnicals')} style={{ marginBottom: '1.5rem' }}>
      <p style={{ margin: '0 0 0.75rem' }}>
        {data.as_of
          ? t('instrumentTechnicals.summaryTo', {
              count: quality.data_points,
              date: data.as_of,
            })
          : t('instrumentTechnicals.summary', { count: quality.data_points })}
      </p>
      {quality.warnings.length > 0 && (
        <div
          role="alert"
          aria-label={t('instrumentTechnicals.dataQuality')}
          className={surfaceStyles.surfaceCard}
          style={{ borderLeft: '4px solid #d97706', marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>
            {t('instrumentTechnicals.dataQuality')}
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {quality.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {data.signals.length > 0 && (
        <div
          aria-label={t('instrumentTechnicals.signals')}
          className={surfaceStyles.surfaceCard}
          style={{ marginBottom: '1rem' }}
        >
          <h3 className={surfaceStyles.surfaceCardTitle}>
            {t('instrumentTechnicals.chartShows')}
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {data.signals.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
            {inRouterContext ? (
              <Link to={`${GLOSSARY_PATH}#${TECHNICALS_GLOSSARY_ANCHOR}`}>
                {t('instrumentTechnicals.termsLink')}
              </Link>
            ) : (
              <a href={`${GLOSSARY_PATH}#${TECHNICALS_GLOSSARY_ANCHOR}`}>
                {t('instrumentTechnicals.termsLink')}
              </a>
            )}
          </p>
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
            <h3 className={surfaceStyles.surfaceCardTitle}>
              <span>{section.title}</span>
              {section.term && <TermTip term={section.term} />}
            </h3>
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
                      <span>{row.label}</span>
                      {row.term && <TermTip term={row.term} />}
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
