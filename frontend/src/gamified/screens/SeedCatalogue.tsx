import { useEffect, useMemo, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { getQuotes } from '../../api';
import type { QuoteRow } from '../../types';
import { usePlotData } from '../PlotDataContext';
import { formatPct, seedKindFor } from '../plotModel';
import { useWatchlists } from '../../lib/watchlistStore';
import { symbolUnit } from '../../lib/quoteUnit';
import { priceDecimals } from '../../utils/priceFormatting';

/**
 * Last price with its currency or unit, using the same unit rules as the
 * classic Watchlist page (#7203): "92.50 GBX", "10878 pts", "0.74000 GBP".
 */
function QuotePrice({ row }: { row: QuoteRow }) {
  const { t } = useTranslation();
  if (row.last === null) return <span className={styles.cropValue}>—</span>;
  const unit = symbolUnit(row.symbol, row.currency, row.quoteType);
  const price = row.last.toFixed(priceDecimals(row.symbol, row.last));
  return (
    <span className={styles.cropValue}>
      {price} {unit === '—' ? t('plot.seeds.unitUnknown') : unit}
    </span>
  );
}

function QuoteChange({ change }: { change: number | null }) {
  return (
    <span className={change !== null && change < 0 ? styles.loss : styles.gain}>
      {change === null ? '—' : formatPct(change)}
    </span>
  );
}

/** A packet for something you could actually hold. */
function SeedPacket({
  row,
  ownedCropId,
  basePath,
}: {
  row: QuoteRow;
  ownedCropId: string | undefined;
  basePath: string;
}) {
  const { t } = useTranslation();
  const isOwned = ownedCropId !== undefined;
  return (
    <div className={styles.seedCard}>
      <span className={styles.seedTitle}>{row.symbol}</span>
      <span className={styles.seedOwn}>
        {row.name || t('plot.seeds.unnamed')}
      </span>
      {/* Plain fact, no sprout and no "yet": not owning something is not a
          task left undone (#7203). */}
      <span className={styles.seedOwn}>
        {isOwned ? t('plot.seeds.alreadyGrowing') : t('plot.seeds.notInPlot')}
      </span>
      <QuotePrice row={row} />
      <QuoteChange change={row.changePct} />
      <span className={styles.seedAction}>
        <Link
          className={styles.chipButton}
          to={
            isOwned
              ? `${basePath}/crops/${encodeURIComponent(ownedCropId)}`
              : `/instrument?ticker=${encodeURIComponent(row.symbol)}`
          }
        >
          {isOwned ? t('plot.seeds.inspectCrop') : t('plot.seeds.readPacket')}
        </Link>
      </span>
    </div>
  );
}

/** An index, FX rate or future: a market reading, with no call to action. */
function WeatherReading({ row }: { row: QuoteRow }) {
  const { t } = useTranslation();
  return (
    <div className={styles.seedCard}>
      <span className={styles.seedTitle}>{row.symbol}</span>
      <span className={styles.seedOwn}>
        {row.name || t('plot.seeds.unnamed')}
      </span>
      <QuotePrice row={row} />
      <QuoteChange change={row.changePct} />
    </div>
  );
}

/** Live quotes for the active watchlist symbols, with a retry. */
function useWatchlistQuotes(symbols: string[]) {
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Don't show the previous list's packets (or count) for the new one.
    setRows([]);
    if (symbols.length === 0) {
      setLoading(false);
      return () => controller.abort();
    }
    getQuotes(symbols, controller.signal)
      .then((quotes) => {
        if (cancelled) return;
        setRows(quotes);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : String(cause));
        setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [symbols, retryToken]);

  const retry = () => setRetryToken((token) => token + 1);
  return { rows, error, loading, retry };
}

/**
 * The seed shed: the watchlist split into seed packets (things you could
 * hold) and the weather (indices, FX and futures — conditions, not crops).
 */
export default function SeedCatalogue({ basePath }: { basePath: string }) {
  const { t } = useTranslation();
  const { snapshot } = usePlotData();
  // The list currently selected on the classic Watchlist tab, so the two
  // views show the same symbols rather than drifting apart. Subscribed, so
  // switching or editing that list re-quotes here without a remount.
  const symbols = useWatchlists().active.symbols;
  const { rows, error, loading, retry } = useWatchlistQuotes(symbols);

  const seeds = rows.filter(
    (row) => seedKindFor(row.symbol, row.quoteType) === 'seed'
  );
  const weather = rows.filter(
    (row) => seedKindFor(row.symbol, row.quoteType) === 'weather'
  );

  // Maps a watchlist symbol to the first crop holding it, so "already
  // growing" can link at a holding rather than a bare ticker.
  const ownedByTicker = useMemo(() => {
    const index = new Map<string, string>();
    for (const crop of snapshot.crops) {
      const key = crop.ticker.toUpperCase();
      if (!index.has(key)) index.set(key, crop.id);
    }
    return index;
  }, [snapshot.crops]);

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.seeds.title')}</h2>
        <p className={styles.sectionNote}>{t('plot.seeds.intro')}</p>
        {/* Always visible, not just in the empty state: the seed shed reads
            the watchlist, the classic page edits it (#7203). */}
        <p className={styles.sectionNote}>
          <Trans
            i18nKey="plot.seeds.manage"
            components={{ txlink: <Link to="/watchlist" /> }}
          />
        </p>
      </section>

      {error && !loading && (
        <div className={styles.errorBanner} role="alert">
          <p style={{ margin: 0 }}>{t('plot.seeds.loadError', { error })}</p>
          <button
            type="button"
            className={styles.chipButton}
            onClick={retry}
            style={{ marginTop: '0.5rem' }}
          >
            {t('plot.seeds.tryAgain')}
          </button>
        </div>
      )}

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        {/* No count until the quotes are in: "(0)" while loading is a false
            claim (#7203). */}
        <h2 className={styles.panelTitle}>
          {loading
            ? t('plot.seeds.availableTitle')
            : t('plot.seeds.available', { count: seeds.length })}
        </h2>
        {loading ? (
          <p className={styles.loading} role="status">
            {t('plot.seeds.loading')}
          </p>
        ) : error ? null : symbols.length === 0 ? (
          <p className={styles.emptyState}>
            <Trans
              i18nKey="plot.seeds.emptyWatchlist"
              components={{ txlink: <Link to="/watchlist" /> }}
            />
          </p>
        ) : rows.length === 0 ? (
          <p className={styles.emptyState}>
            <Trans
              i18nKey="plot.seeds.noQuotes"
              components={{ txlink: <Link to="/watchlist" /> }}
            />
          </p>
        ) : seeds.length === 0 ? (
          <p className={styles.emptyState}>{t('plot.seeds.noSeeds')}</p>
        ) : (
          <div className={styles.seedGrid}>
            {seeds.map((row) => (
              <SeedPacket
                key={row.symbol}
                row={row}
                ownedCropId={ownedByTicker.get(row.symbol.toUpperCase())}
                basePath={basePath}
              />
            ))}
          </div>
        )}
      </section>

      {!loading && weather.length > 0 && (
        <section
          className={`${styles.panel} ${styles.panelGlow}`}
          aria-labelledby="plot-weather-title"
        >
          <h2 id="plot-weather-title" className={styles.panelTitle}>
            {t('plot.seeds.weatherTitle', { count: weather.length })}
          </h2>
          <p className={styles.sectionNote}>{t('plot.seeds.weatherNote')}</p>
          <div className={styles.seedGrid}>
            {weather.map((row) => (
              <WeatherReading key={row.symbol} row={row} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
