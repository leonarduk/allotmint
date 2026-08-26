import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { getQuotes } from '../../api';
import type { QuoteRow } from '../../types';
import { usePlotData } from '../PlotDataContext';
import { formatPct } from '../plotModel';

/**
 * The same localStorage key the classic Watchlist page uses, so the seed
 * catalogue and the watchlist are two views of one list rather than two
 * lists that drift apart.
 */
const WATCHLIST_KEY = 'watchlistSymbols';
const DEFAULT_SYMBOLS = '^FTSE,^NDX,^GSPC,VUSA.L,IWDA.AS';

function readWatchlist(): string[] {
  if (typeof window === 'undefined') return DEFAULT_SYMBOLS.split(',');
  const stored = window.localStorage.getItem(WATCHLIST_KEY) || DEFAULT_SYMBOLS;
  return stored
    .split(',')
    .map((symbol) => symbol.trim())
    .filter(Boolean);
}

/** Seed packets: watchlist symbols you could sow, priced from live quotes. */
export default function SeedCatalogue({ basePath }: { basePath: string }) {
  const { snapshot } = usePlotData();
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const symbols = useMemo(readWatchlist, []);
  const retry = () => setRetryToken((token) => token + 1);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);
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
        <h2 className={styles.panelTitle}>Seed catalogue</h2>
        <p className={styles.sectionNote}>
          Your watchlist as seed packets — the same list the classic Watchlist
          page reads, priced from live quotes. Nothing here places a trade.
        </p>
      </section>

      {error && !loading && (
        <div className={styles.errorBanner} role="alert">
          <p style={{ margin: 0 }}>Could not load quotes: {error}</p>
          <button
            type="button"
            className={styles.chipButton}
            onClick={retry}
            style={{ marginTop: '0.5rem' }}
          >
            Try again
          </button>
        </div>
      )}

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Available seed ({rows.length})</h2>
        {loading ? (
          <p className={styles.loading} role="status">
            Checking the seed trays…
          </p>
        ) : error ? null : symbols.length === 0 ? (
          <p className={styles.emptyState}>
            Your watchlist is empty — add a stock to see it here. You can add
            one in the <Link to="/watchlist">classic watchlist</Link>.
          </p>
        ) : rows.length === 0 ? (
          <p className={styles.emptyState}>
            No quotes came back for your watchlist symbols. Try the{' '}
            <Link to="/watchlist">classic watchlist</Link> to check them.
          </p>
        ) : (
          <div className={styles.seedGrid}>
            {rows.map((row) => {
              const ownedCropId = ownedByTicker.get(row.symbol.toUpperCase());
              const isOwned = ownedCropId !== undefined;
              const change = row.changePct;
              return (
                <div key={row.symbol} className={styles.seedCard}>
                  <span className={styles.seedTitle}>
                    <span aria-hidden="true">🌱</span> {row.symbol}
                  </span>
                  <span className={styles.seedOwn}>
                    {row.name || 'Unnamed instrument'}
                  </span>
                  <span className={styles.seedOwn}>
                    {isOwned ? 'Already growing in your plot' : 'Not sown yet'}
                  </span>
                  <span className={styles.cropValue}>
                    {row.last === null ? '—' : row.last.toFixed(2)}
                  </span>
                  <span
                    className={
                      change !== null && change < 0 ? styles.loss : styles.gain
                    }
                  >
                    {change === null ? '—' : formatPct(change)}
                  </span>
                  <span className={styles.seedAction}>
                    <Link
                      className={styles.chipButton}
                      to={
                        isOwned
                          ? `${basePath}/crops/${encodeURIComponent(ownedCropId)}`
                          : `/instrument?ticker=${encodeURIComponent(row.symbol)}`
                      }
                    >
                      {isOwned ? 'Inspect crop' : 'Read the packet'}
                    </Link>
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
