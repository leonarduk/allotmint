import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { getInstrumentAllocation, refreshInstrumentLookThrough } from '../api';
import type {
  InstrumentAllocation,
  LookThroughExposure,
  LookThroughHolding,
} from '../types';
import { percent } from '../lib/money';
import { foldWeightRows } from '../lib/lookThrough';
import surfaceStyles from '../styles/surface.module.css';

const BAR_COLOR = '#8884d8';

const cell = { padding: '0.35rem 0.5rem' } as const;
const numCell = {
  ...cell,
  textAlign: 'right' as const,
  whiteSpace: 'nowrap' as const,
};

/** Label / bar / percentage rows, largest first, for a country or sector breakdown (#9974). */
export function WeightBars({
  title,
  rows: allRows,
}: {
  title: string;
  rows: { label: string; weight_pct: number }[];
}) {
  const { t } = useTranslation();
  const rows = foldWeightRows(allRows, (count) =>
    t('lookThrough.otherRows', { count })
  );
  const max = Math.max(...rows.map((r) => r.weight_pct), 0);
  return (
    <div className={surfaceStyles.surfaceCard}>
      <h3 className={surfaceStyles.surfaceCardTitle}>{title}</h3>
      <table
        aria-label={title}
        style={{ width: '100%', borderCollapse: 'collapse' }}
      >
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th
                scope="row"
                style={{
                  ...cell,
                  textAlign: 'left',
                  fontWeight: 500,
                  paddingLeft: 0,
                }}
              >
                {row.label}
              </th>
              <td style={{ ...cell, width: '45%' }} aria-hidden="true">
                <div
                  style={{
                    height: '0.6rem',
                    borderRadius: '0.3rem',
                    background: BAR_COLOR,
                    width: `${max > 0 ? Math.max((row.weight_pct / max) * 100, 1) : 0}%`,
                  }}
                />
              </td>
              <td style={{ ...numCell, paddingRight: 0, fontWeight: 600 }}>
                {percent(row.weight_pct, 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const holdingName = (h: LookThroughHolding, t: (key: string) => string) =>
  h.kind === 'other'
    ? t('lookThrough.otherInFunds')
    : h.kind === 'cash'
      ? t('lookThrough.cash')
      : h.name;

/** Underlying holdings across direct shares and funds, with where each exposure comes from (#9974). */
export function LookThroughHoldingsTable({
  holdings,
  format,
}: {
  holdings: LookThroughHolding[];
  format: (value: number) => string;
}) {
  const { t } = useTranslation();
  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        aria-label={t('lookThrough.holdingsTitle')}
        style={{ width: '100%', borderCollapse: 'collapse' }}
      >
        <thead>
          <tr>
            <th style={{ ...cell, textAlign: 'left' }}>
              {t('lookThrough.holding')}
            </th>
            <th style={numCell}>{t('lookThrough.total')}</th>
            <th style={numCell}>{t('lookThrough.weight')}</th>
            <th style={numCell}>{t('lookThrough.direct')}</th>
            <th style={numCell}>{t('lookThrough.viaFunds')}</th>
            <th style={{ ...cell, textAlign: 'left' }}>
              {t('lookThrough.heldThrough')}
            </th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr
              key={h.key}
              style={{ borderTop: '1px solid rgba(128,128,128,0.25)' }}
            >
              <td style={cell}>{holdingName(h, t)}</td>
              <td style={{ ...numCell, fontWeight: 600 }}>
                {format(h.value_gbp)}
              </td>
              <td style={numCell}>{percent(h.weight_pct)}</td>
              <td style={numCell}>
                {h.direct_value_gbp ? format(h.direct_value_gbp) : '—'}
              </td>
              <td style={numCell}>
                {h.via_funds_value_gbp ? format(h.via_funds_value_gbp) : '—'}
              </td>
              <td style={{ ...cell, fontSize: '0.85em' }}>
                {h.kind === 'cash'
                  ? '—'
                  : h.sources.map((s, i) => (
                      <span key={s.ticker}>
                        {i > 0 && ', '}
                        <Link to={`/research/${encodeURIComponent(s.ticker)}`}>
                          {s.ticker}
                        </Link>
                      </span>
                    ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Which funds were looked through (with data dates) and which were not (#9974). */
export function LookThroughCoverageNote({
  coverage,
  format,
}: {
  coverage: LookThroughExposure['coverage'];
  format: (value: number) => string;
}) {
  const { t } = useTranslation();
  const dates = coverage.funds
    .map((f) => f.as_of)
    .filter((d): d is string => !!d)
    .sort();
  return (
    <div
      className="mb-4 text-sm text-gray-600"
      data-testid="look-through-coverage"
    >
      <p>
        {t('lookThrough.coverage', {
          funds: coverage.funds.length,
          value: format(coverage.looked_through_value_gbp),
          from: dates[0] ?? '—',
          to: dates[dates.length - 1] ?? '—',
        })}
      </p>
      {coverage.not_covered.length > 0 && (
        <p className="text-amber-700" data-testid="look-through-not-covered">
          {t('lookThrough.notCovered', {
            value: format(coverage.not_covered_value_gbp),
            tickers: coverage.not_covered.map((f) => f.ticker).join(', '),
          })}
        </p>
      )}
    </div>
  );
}

const sourceName = (source: string | null, t: (key: string) => string) =>
  source === 'justetf'
    ? 'justETF'
    : source === 'morningstar'
      ? 'Morningstar'
      : source === 'manual'
        ? t('lookThrough.manualSource')
        : (source ?? '—');

function AllocationSummary({ data }: { data: InstrumentAllocation }) {
  const { t } = useTranslation();
  if (data.kind === 'fund') {
    return (
      <p
        className={surfaceStyles.surfaceMuted}
        data-testid="instrument-allocation-source"
      >
        {t('lookThrough.fundSource', {
          date: data.as_of ?? '—',
          holdings: data.holdings_count ?? '—',
        })}
      </p>
    );
  }
  const key =
    data.kind === 'security'
      ? 'lookThrough.singleSecurity'
      : data.kind === 'cash'
        ? 'lookThrough.cashInstrument'
        : 'lookThrough.fundUncovered';
  return (
    <p
      className={surfaceStyles.surfaceMuted}
      data-testid="instrument-allocation-source"
    >
      {t(key)}
    </p>
  );
}

/** Where a fund's data came from, when it was fetched, and a button to fetch it again now. */
function SourceAndRefresh({
  data,
  refreshing,
  status,
  onRefresh,
}: {
  data: InstrumentAllocation;
  refreshing: boolean;
  status: { ok: boolean; text: string } | null;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '0.75rem',
      }}
      data-testid="instrument-allocation-provenance"
    >
      {data.source && (
        <span className={surfaceStyles.surfaceMuted}>
          {t('lookThrough.sourceLabel')}:{' '}
          {data.source_url ? (
            <a href={data.source_url} target="_blank" rel="noopener noreferrer">
              {sourceName(data.source, t)}
            </a>
          ) : (
            sourceName(data.source, t)
          )}
          {' · '}
          {t('lookThrough.lastUpdated', { date: data.fetched ?? '—' })}
        </span>
      )}
      <button type="button" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? t('lookThrough.refreshing') : t('lookThrough.refresh')}
      </button>
      {status && (
        <span
          role="status"
          style={{ color: status.ok ? undefined : '#c2410c' }}
        >
          {status.text}
        </span>
      )}
    </div>
  );
}

function TopHoldingsCard({ data }: { data: InstrumentAllocation }) {
  const { t } = useTranslation();
  const covered = data.top_holdings.reduce((sum, h) => sum + h.weight_pct, 0);
  return (
    <div className={surfaceStyles.surfaceCard} style={{ gridColumn: '1 / -1' }}>
      <h3 className={surfaceStyles.surfaceCardTitle}>
        {t('lookThrough.topHoldings')}
      </h3>
      <table
        aria-label={t('lookThrough.topHoldings')}
        style={{ width: '100%', borderCollapse: 'collapse' }}
      >
        <thead>
          <tr>
            <th style={{ ...cell, textAlign: 'left', paddingLeft: 0 }}>
              {t('lookThrough.holding')}
            </th>
            <th style={{ ...cell, textAlign: 'left' }}>
              {t('lookThrough.country')}
            </th>
            <th style={{ ...cell, textAlign: 'left' }}>
              {t('lookThrough.sector')}
            </th>
            <th style={{ ...numCell, paddingRight: 0 }}>
              {t('lookThrough.weight')}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.top_holdings.map((h) => (
            <tr
              key={`${h.isin ?? ''}-${h.name}`}
              style={{ borderTop: '1px solid rgba(128,128,128,0.25)' }}
            >
              <td style={{ ...cell, paddingLeft: 0 }}>{h.name}</td>
              <td style={cell}>{h.country ?? '—'}</td>
              <td style={cell}>{h.sector ?? '—'}</td>
              <td style={{ ...numCell, paddingRight: 0 }}>
                {percent(h.weight_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.kind === 'fund' && covered < 99.5 && (
        <p
          className={surfaceStyles.surfaceMuted}
          style={{ marginTop: '0.5rem' }}
        >
          {t('lookThrough.topHoldingsCovered', { pct: percent(covered, 1) })}
        </p>
      )}
    </div>
  );
}

/** The Research page's Allocation tab: where an instrument's money is invested (#9974). */
export function InstrumentAllocationPanel({ ticker }: { ticker: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<InstrumentAllocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState<{
    ok: boolean;
    text: string;
  } | null>(null);

  const handleRefresh = () => {
    setRefreshing(true);
    setRefreshStatus(null);
    refreshInstrumentLookThrough(ticker)
      .then((result) => {
        setData(result.allocation);
        setRefreshStatus(
          result.updated
            ? {
                ok: true,
                text: t('lookThrough.refreshUpdated', {
                  source: sourceName(result.allocation.source, t),
                }),
              }
            : { ok: false, text: t('lookThrough.refreshNotCovered') }
        );
      })
      .catch((e) =>
        setRefreshStatus({
          ok: false,
          text: t('lookThrough.refreshFailed', {
            message: e instanceof Error ? e.message : String(e),
          }),
        })
      )
      .finally(() => setRefreshing(false));
  };

  useEffect(() => {
    if (!ticker) return;
    setRefreshStatus(null);
    const controller = new AbortController();
    setData(null);
    setError(null);
    getInstrumentAllocation(ticker, controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, [ticker]);

  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!data) return <div>{t('app.loading')}</div>;
  return (
    <div>
      <AllocationSummary data={data} />
      {(data.kind === 'fund' || data.kind === 'fund_uncovered') && (
        <SourceAndRefresh
          data={data}
          refreshing={refreshing}
          status={refreshStatus}
          onRefresh={handleRefresh}
        />
      )}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1rem',
          marginTop: '0.75rem',
        }}
      >
        <WeightBars title={t('lookThrough.countries')} rows={data.countries} />
        <WeightBars title={t('lookThrough.sectors')} rows={data.sectors} />
        {data.top_holdings.length > 0 && <TopHoldingsCard data={data} />}
      </div>
    </div>
  );
}
