import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getOwners,
  getTrendWatchLatest,
  runTrendWatch,
  setTrendWatchMute,
} from '../api';
import type {
  OwnerSummary,
  TrendWatchBacktest,
  TrendWatchItem,
  TrendWatchReport,
  TrendWatchVerdict,
} from '../types';
import { OwnerSelector } from './OwnerSelector';
import { sanitizeOwners } from '../utils/owners';
import styles from './TrendWatchPanel.module.css';

interface Props {
  /** Owner to show first; the panel falls back to the first owner listed. */
  owner?: string;
}

const SIGNAL_LABELS: Record<string, string> = {
  death_cross: '50-day average below the 200-day (death cross)',
  below_falling_sma200: 'Price below a falling 200-day average',
  rs_new_low: 'Relative strength at a new 6-month low',
  lower_highs_lows: 'Lower high and lower low',
  break_52w_low: 'Closed below its previous 52-week low',
  macd_negative: 'MACD below zero',
};

const VERDICT_CLASS: Record<TrendWatchVerdict, string> = {
  idiosyncratic_deterioration: styles.idiosyncratic,
  market_wide_move: styles.market,
  data_problem: styles.data,
  inconclusive: styles.inconclusive,
};

const DEFAULT_DISCLAIMER =
  'A review list, not trade instructions: it describes what changed in a holding’s chart and what was found about why. The decision is yours.';

function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? '–' : `${(value * 100).toFixed(digits)}%`;
}

function gbp(value: number | null | undefined): string {
  return value == null
    ? '–'
    : value.toLocaleString('en-GB', {
        style: 'currency',
        currency: 'GBP',
        maximumFractionDigits: 0,
      });
}

function errorText(err: unknown, fallback: string): string {
  return (err as { message?: string } | undefined)?.message || fallback;
}

function HitRate({ backtest }: { backtest: TrendWatchBacktest | null }) {
  const { t } = useTranslation();
  if (!backtest) return null;
  if (!backtest.tickers_tested) {
    return (
      <section
        className={styles.hitRate}
        aria-labelledby="trend-watch-hit-rate"
      >
        <h3 id="trend-watch-hit-rate">
          {t('trendWatch.hitRate.title', 'Track record of this detector')}
        </h3>
        <p>
          {t(
            'trendWatch.hitRate.noHistory',
            'Not enough price history in these holdings to measure it yet.'
          )}
        </p>
      </section>
    );
  }
  const entries = Object.entries(backtest.horizons);
  const totalBasis = backtest.return_basis.total ?? 0;
  const priceBasis = backtest.return_basis.price ?? 0;
  // Horizons where a flag has done no better than an ordinary week.
  const noEdge = entries
    .filter(
      ([, h]) =>
        h.flag_fall_rate != null &&
        h.base_rate != null &&
        h.flag_fall_rate <= h.base_rate
    )
    .map(([label]) => label);
  return (
    <section className={styles.hitRate} aria-labelledby="trend-watch-hit-rate">
      <h3 id="trend-watch-hit-rate">
        {t('trendWatch.hitRate.title', 'Track record of this detector')}
      </h3>
      <p>
        {t(
          'trendWatch.hitRate.description',
          'Replayed weekly over {{count}} of your holdings: how often a flag was followed by a further fall, against how often any week was.',
          { count: backtest.tickers_tested }
        )}
      </p>
      <table className={styles.hitTable}>
        <thead>
          <tr>
            <th scope="col">
              {t('trendWatch.hitRate.horizon', 'Over the next')}
            </th>
            <th scope="col">
              {t('trendWatch.hitRate.afterFlag', 'Fell after a flag')}
            </th>
            <th scope="col">
              {t('trendWatch.hitRate.base', 'Fell in any week')}
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([label, h]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>
                {pct(h.flag_fall_rate)}{' '}
                <span className={styles.muted}>
                  {t('trendWatch.hitRate.flags', '({{count}} flags)', {
                    count: h.flags,
                  })}
                </span>
              </td>
              <td>{pct(h.base_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={styles.muted}>
        {t(
          'trendWatch.hitRate.basis',
          'Falls measured on total return (dividends reinvested) for {{total}} holdings and on price only for {{price}}, which have no stored dividend history.',
          { total: totalBasis, price: priceBasis }
        )}
      </p>
      {noEdge.length > 0 && (
        <p className={styles.caution} role="note">
          {t(
            'trendWatch.hitRate.noEdge',
            'Over {{horizons}}, a flag on these holdings has been no better than the base rate at foreseeing a further fall. Treat the list as prompts to look, not forecasts.',
            { horizons: noEdge.join(', ') }
          )}
        </p>
      )}
    </section>
  );
}

function Evidence({ item }: { item: TrendWatchItem }) {
  const { t } = useTranslation();
  const inv = item.investigation;
  return (
    <details className={styles.evidence}>
      <summary>{t('trendWatch.evidence.toggle', 'Evidence')}</summary>
      {inv.summary && <p>{inv.summary}</p>}
      {item.data_issues?.length ? (
        <ul aria-label={t('trendWatch.evidence.dataIssues', 'Data issues')}>
          {item.data_issues.map((issue, i) => (
            <li key={issue.id ?? i}>
              <strong>{issue.type}</strong> ({issue.severity}):{' '}
              {issue.description}
              {issue.suggested_fix ? ` ${issue.suggested_fix}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
      <ul aria-label={t('trendWatch.evidence.findings', 'Findings')}>
        {inv.evidence.map((e, i) => (
          <li key={`${e.tool}-${i}`}>
            <code>{e.tool}</code>: {e.finding}
            {e.value ? ` — ${e.value}` : ''}
            {e.return_basis && e.return_basis !== 'n/a'
              ? ` (${t('trendWatch.evidence.basis', 'return basis: {{basis}}', { basis: e.return_basis })})`
              : ''}
            {e.source ? (
              /^https?:\/\//.test(e.source) ? (
                <>
                  {' '}
                  (
                  <a href={e.source} target="_blank" rel="noreferrer noopener">
                    {t('trendWatch.evidence.source', 'source')}
                  </a>
                  )
                </>
              ) : (
                ` (${e.source})`
              )
            ) : null}
          </li>
        ))}
      </ul>
      {inv.tool_calls.length > 0 && (
        <>
          <h4>{t('trendWatch.evidence.toolCalls', 'Tool calls')}</h4>
          <ul>
            {inv.tool_calls.map((c, i) => (
              <li key={`${c.tool}-${i}`}>
                <code>
                  {c.tool}({JSON.stringify(c.arguments)})
                </code>
                {c.is_error
                  ? ` ${t('trendWatch.evidence.failed', '(failed)')}`
                  : ''}
                : {c.result}
              </li>
            ))}
          </ul>
        </>
      )}
      {inv.notes.length > 0 && (
        <ul
          className={styles.notes}
          aria-label={t('trendWatch.evidence.notes', 'Notes')}
        >
          {inv.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </details>
  );
}

function ItemCard({
  item,
  onToggleMute,
  busy,
}: {
  item: TrendWatchItem;
  onToggleMute: (item: TrendWatchItem) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const ctx = item.context;
  return (
    <li
      className={`${styles.item} ${item.muted ? styles.mutedItem : ''}`}
      data-testid={`trend-item-${item.ticker}`}
    >
      <div className={styles.itemHeader}>
        <span className={styles.rank}>{item.rank}</span>
        <strong>{item.ticker}</strong>
        {item.name && item.name !== item.ticker && (
          <span className={styles.muted}>{item.name}</span>
        )}
        <span className={`${styles.badge} ${VERDICT_CLASS[item.verdict]}`}>
          {t(`trendWatch.verdict.${item.verdict}`, item.verdict_label)}
        </span>
        {/* Detection-only verdicts (no model, a failed call or over the cap) are
            labelled, so they are not mistaken for an investigated explanation. */}
        {item.verdict !== 'data_problem' &&
          item.investigation.status !== 'ok' && (
            <span className={`${styles.badge} ${styles.inconclusive}`}>
              {t('trendWatch.notInvestigated', 'Not investigated')}
            </span>
          )}
        {item.muted && (
          <span className={styles.muted}>
            {t('trendWatch.mutedLabel', 'Long-term holding')}
          </span>
        )}
        <button
          type="button"
          className={styles.muteButton}
          onClick={() => onToggleMute(item)}
          disabled={busy}
          aria-pressed={item.muted}
        >
          {item.muted
            ? t('trendWatch.unmute', 'Unmute')
            : t('trendWatch.mute', 'Mute (long-term holding)')}
        </button>
      </div>
      <p className={styles.signals}>
        {item.detection.active.map((s) => (
          <span
            key={s}
            className={
              item.detection.new.includes(s) ? styles.newSignal : styles.signal
            }
          >
            {SIGNAL_LABELS[s] ?? s}
            {item.detection.new.includes(s)
              ? ` · ${t('trendWatch.new', 'new')}`
              : ''}
          </span>
        ))}
      </p>
      <p className={styles.context}>
        {t(
          'trendWatch.context',
          '{{value}} ({{share}} of the portfolio); book cost {{cost}}, gain {{gain}}.',
          {
            value: gbp(ctx.market_value_gbp),
            share: pct(ctx.portfolio_share, 1),
            cost: gbp(ctx.cost_basis_gbp),
            gain: pct(ctx.gain_pct, 1),
          }
        )}{' '}
        {ctx.cgt_note}
      </p>
      <Evidence item={item} />
    </li>
  );
}

export default function TrendWatchPanel({ owner: initialOwner }: Props) {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState(initialOwner ?? '');
  const [report, setReport] = useState<TrendWatchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [muting, setMuting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getOwners()
      .then((list) => {
        if (cancelled) return;
        const clean = sanitizeOwners(list);
        setOwners(clean);
        setOwner((current) => current || clean[0]?.owner || '');
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            errorText(
              err,
              t('trendWatch.ownersError', 'Could not load owners.')
            )
          );
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    if (!owner) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTrendWatchLatest(owner)
      .then((latest) => {
        if (!cancelled) setReport(latest);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            errorText(
              err,
              t(
                'trendWatch.loadError',
                'Could not load the trend-watch report.'
              )
            )
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [owner, t]);

  const handleRun = useCallback(async () => {
    if (!owner) return;
    setRunning(true);
    setError(null);
    try {
      setReport(await runTrendWatch(owner));
    } catch (err) {
      setError(
        errorText(err, t('trendWatch.runError', 'The trend-watch run failed.'))
      );
    } finally {
      setRunning(false);
    }
  }, [owner, t]);

  const handleToggleMute = useCallback(
    async (item: TrendWatchItem) => {
      setMuting(item.ticker);
      setError(null);
      try {
        const { mutes } = await setTrendWatchMute(
          owner,
          item.ticker,
          !item.muted
        );
        setReport(
          (current) =>
            current && {
              ...current,
              mutes,
              items: current.items.map((it) => ({
                ...it,
                // The server stores mutes upper-cased.
                muted: mutes.includes(it.ticker.toUpperCase()),
              })),
            }
        );
      } catch (err) {
        setError(
          errorText(
            err,
            t('trendWatch.muteError', 'Could not update the mute list.')
          )
        );
      } finally {
        setMuting(null);
      }
    },
    [owner, t]
  );

  return (
    <section className={styles.panel} aria-labelledby="trend-watch-title">
      <div className={styles.heading}>
        <div>
          <h2 id="trend-watch-title">{t('trendWatch.title', 'Trend watch')}</h2>
          <p className={styles.disclaimer}>
            {report?.disclaimer ?? DEFAULT_DISCLAIMER}
          </p>
        </div>
        <div className={styles.controls}>
          {owners.length > 1 && (
            <OwnerSelector
              owners={owners}
              selected={owner}
              onSelect={setOwner}
            />
          )}
          <button
            type="button"
            onClick={handleRun}
            disabled={!owner || running}
          >
            {running
              ? t('trendWatch.running', 'Running…')
              : t('trendWatch.run', 'Run now')}
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">{t('trendWatch.loading', 'Loading trend watch…')}</p>
      ) : !report ? (
        <p>
          {t(
            'trendWatch.empty',
            'No trend-watch report yet. Run it to check your holdings.'
          )}
        </p>
      ) : (
        <>
          <p className={styles.muted}>
            {t(
              'trendWatch.summary',
              'Run {{date}}: {{checked}} holdings checked, {{count}} to review.',
              {
                date: report.run_date,
                checked: report.holdings_checked,
                count: report.items.length,
              }
            )}
          </p>
          {report.items.length === 0 ? (
            <p>
              {t(
                'trendWatch.none',
                'No holding has newly turned down since the last run.'
              )}
            </p>
          ) : (
            <ol className={styles.list}>
              {report.items.map((item) => (
                <ItemCard
                  key={item.ticker}
                  item={item}
                  onToggleMute={handleToggleMute}
                  busy={muting === item.ticker}
                />
              ))}
            </ol>
          )}
          <HitRate backtest={report.backtest} />
        </>
      )}
    </section>
  );
}
