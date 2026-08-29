import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getTradingPageData } from '../api';
import type { TradingAgentSettings, TradingSignal } from '../types';
import { InstrumentDetail } from '../components/InstrumentDetail';
import BackendUnavailableCard from '../components/BackendUnavailableCard';
import useFetchWithRetry from '../hooks/useFetchWithRetry';
import TableRowsSkeleton from '../components/skeletons/TableRowsSkeleton';
import TextSkeleton from '../components/skeletons/TextSkeleton';
import LoadingStatus from '../components/skeletons/LoadingStatus';
import tableStyles from '../styles/table.module.css';
import { MAX_TRADING_SIGNAL_ROWS } from '../constants/renderLimits';
import styles from './Trading.module.css';

const SIGNAL_COLUMN_COUNT = 5;

// Threshold labels are static copy, not data -- they render immediately
// regardless of loading state (see below), so only the value column needs a
// skeleton while `getTradingPageData` is in flight.
const THRESHOLDS: {
  label: string;
  key: keyof TradingAgentSettings;
  suffix?: string;
}[] = [
  { label: 'RSI buy below', key: 'rsi_buy' },
  { label: 'RSI sell above', key: 'rsi_sell' },
  { label: 'RSI lookback', key: 'rsi_window', suffix: ' days' },
  { label: 'Short moving average', key: 'ma_short_window', suffix: ' days' },
  { label: 'Long moving average', key: 'ma_long_window', suffix: ' days' },
  { label: 'Maximum P/E', key: 'pe_max' },
  { label: 'Maximum debt/equity', key: 'de_max' },
  { label: 'Minimum Sharpe ratio', key: 'min_sharpe' },
  { label: 'Maximum volatility', key: 'max_volatility' },
];

export default function Trading() {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<TradingSignal | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const handleRetry = useCallback(() => setRetryNonce((n) => n + 1), []);

  // `getTradingPageData` bundles both the strategy-threshold settings and the
  // signal list in a single slow backend call (~10s+, see #7229/#3424), so
  // the two sections below can't load independently — but the static header
  // above them can render immediately instead of waiting on it too.
  const { data, loading, error } = useFetchWithRetry(
    getTradingPageData,
    500,
    5,
    retryNonce
  );

  const loadingLabel = t('trading.loading');

  const signals = data?.signals ?? [];
  const visibleSignals = signals.slice(0, MAX_TRADING_SIGNAL_ROWS);

  const formatAction = (action: string) => {
    if (!action) {
      return action;
    }
    const lower = action.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  };

  const renderStrength = (confidence?: number | null) => {
    if (confidence == null) {
      return '—';
    }

    const percent = Math.round(confidence * 100);
    let label = 'Weak';
    if (confidence >= 0.75) {
      label = 'Strong';
    } else if (confidence >= 0.5) {
      label = 'Moderate';
    }

    return `${label} (${percent}%)`;
  };

  const renderChecksSkipped = (checksSkipped?: string[]) => {
    if (!checksSkipped || !checksSkipped.length) {
      return null;
    }

    return (
      <span
        className={styles.checksSkippedBadge}
        title={t('trading.checksSkippedTitle', 'Skipped checks: {{checks}}', {
          checks: checksSkipped.join(', '),
        })}
      >
        {t('trading.checksSkippedBadge', 'Checks skipped')}
      </span>
    );
  };

  const renderFactors = (factors?: string[], fallback?: string) => {
    if (factors && factors.length) {
      return (
        <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
          {factors.map((factor, idx) => (
            <li key={idx}>{factor}</li>
          ))}
        </ul>
      );
    }
    if (fallback) {
      return <span>{fallback}</span>;
    }
    return '—';
  };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>
            {t('trading.eyebrow', 'Decision support')}
          </p>
          <h1>{t('trading.title', 'Trading signals')}</h1>
          <p className={styles.intro}>
            {t(
              'trading.description',
              'Review signals generated from momentum, trend and optional risk filters. Signals are informational and are not trade instructions.'
            )}
          </p>
        </div>
        {loading ? (
          // `LoadingStatus` renders a <div>, which is invalid inside this
          // <span> pill badge (and would change how it sizes), so the
          // status role/live-region attributes go directly on the span
          // itself instead of nesting a LoadingStatus wrapper here.
          <span
            className={styles.signalCount}
            role="status"
            aria-live="polite"
            aria-label={loadingLabel}
          >
            <TextSkeleton width="6rem" label="" />
          </span>
        ) : error ? null : (
          <span className={styles.signalCount}>
            {t('trading.signalCount', '{{count}} active signals', {
              count: signals.length,
            })}
          </span>
        )}
      </header>

      {error ? (
        <BackendUnavailableCard onRetry={handleRetry} />
      ) : (
        <>
          <section
            className={styles.settings}
            aria-labelledby="strategy-settings-title"
          >
            <div className={styles.sectionHeading}>
              <div>
                <h2 id="strategy-settings-title">
                  {t('trading.settings.title', 'Active strategy thresholds')}
                </h2>
                <p>
                  {t(
                    'trading.settings.description',
                    'These server-managed settings determine when a signal can be generated.'
                  )}
                </p>
              </div>
              <span className={styles.readOnly}>
                {t('trading.settings.readOnly', 'Read only')}
              </span>
            </div>
            {loading && (
              <LoadingStatus label={loadingLabel}>
                <span aria-hidden="true" />
              </LoadingStatus>
            )}
            <dl className={styles.thresholdGrid}>
              {THRESHOLDS.map(({ label, key, suffix }) => (
                <div key={key} className={styles.threshold}>
                  {/* The label is static copy, not data -- it renders
                      immediately instead of waiting behind the fetch. */}
                  <dt>{label}</dt>
                  <dd>
                    {loading ? (
                      <span aria-hidden="true">
                        <TextSkeleton width="3rem" label="" />
                      </span>
                    ) : data?.settings[key] == null ? (
                      'Not enabled'
                    ) : (
                      `${data.settings[key]}${suffix ?? ''}`
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section aria-labelledby="signals-title">
            <h2 id="signals-title">
              {t('trading.signalsTitle', 'Current signals')}
            </h2>
            {loading ? (
              <LoadingStatus label={loadingLabel}>
                <div className={tableStyles.scrollContainer} aria-hidden="true">
                  <table className={tableStyles.table}>
                    <caption>
                      {t('trading.signalsTableCaption', 'Trading signals')}
                    </caption>
                    <thead>
                      <tr>
                        <th className={tableStyles.cell}>Ticker</th>
                        <th className={tableStyles.cell}>Action</th>
                        <th className={tableStyles.cell}>Strength</th>
                        <th className={tableStyles.cell}>Summary</th>
                        <th className={tableStyles.cell}>Why</th>
                      </tr>
                    </thead>
                    <tbody>
                      <TableRowsSkeleton
                        rows={5}
                        colSpan={SIGNAL_COLUMN_COUNT}
                        label=""
                        cellClassName={tableStyles.cell}
                      />
                    </tbody>
                  </table>
                </div>
              </LoadingStatus>
            ) : !signals.length ? (
              <div className={styles.emptyState}>
                <h3>{t('trading.noSignalsTitle', 'No signals right now')}</h3>
                <p>
                  {t(
                    'trading.noSignalsDescription',
                    'No tracked instrument currently crosses the active thresholds. Signals appear when RSI or moving-average conditions are met and any enabled valuation and risk filters also pass.'
                  )}
                </p>
              </div>
            ) : (
              <div className={tableStyles.scrollContainer}>
                <table className={tableStyles.table}>
                  <caption>
                    {t('trading.signalsTableCaption', 'Trading signals')}
                  </caption>
                  <thead>
                    <tr>
                      <th className={tableStyles.cell}>Ticker</th>
                      <th className={tableStyles.cell}>Action</th>
                      <th className={tableStyles.cell}>Strength</th>
                      <th className={tableStyles.cell}>Summary</th>
                      <th className={tableStyles.cell}>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleSignals.map((s, index) => (
                      <tr key={`${s.ticker}-${index}`}>
                        <td className={tableStyles.cell}>
                          <button
                            type="button"
                            className={tableStyles.clickable}
                            onClick={() => setSelected(s)}
                          >
                            {s.ticker}
                          </button>
                        </td>
                        <td className={tableStyles.cell}>
                          {formatAction(s.action)}
                          {renderChecksSkipped(s.checks_skipped)}
                        </td>
                        <td className={tableStyles.cell}>
                          {renderStrength(s.confidence)}
                        </td>
                        <td className={tableStyles.cell}>{s.reason}</td>
                        <td className={tableStyles.cell}>
                          {renderFactors(s.factors, s.rationale)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!loading && signals.length > MAX_TRADING_SIGNAL_ROWS && (
              <p>
                Showing first {MAX_TRADING_SIGNAL_ROWS.toLocaleString()} signals of{' '}
                {signals.length.toLocaleString()}.
              </p>
            )}
            {selected && (
              <InstrumentDetail
                ticker={selected.ticker}
                name={selected.name ?? selected.ticker}
                currency={selected.currency ?? undefined}
                instrument_type={selected.instrument_type}
                signal={selected}
                onClose={() => setSelected(null)}
              />
            )}
          </section>
        </>
      )}
    </main>
  );
}
