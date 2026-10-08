import { useEffect, useMemo, useState } from 'react';

import { getLiveQuotes, type LiveQuote } from '@/api';

export const LIVE_QUOTE_POLL_MS = 60_000;
// Matches MAX_LIVE_QUOTE_TICKERS in backend/routes/portfolio.py.
export const LIVE_QUOTE_BATCH_SIZE = 100;

const isHidden = () =>
  typeof document !== 'undefined' && document.visibilityState === 'hidden';

/**
 * Poll intraday quotes for `tickers` while the tab is visible.
 *
 * Returns quotes keyed by upper-cased ticker. A ticker with no quote (offline
 * mode, unsupported exchange, provider failure) is simply absent, so callers
 * fall back to the stored close. A failed poll keeps the previous quotes.
 */
export function useLiveQuotes(
  tickers: readonly string[],
  pollMs: number = LIVE_QUOTE_POLL_MS
): Record<string, LiveQuote> {
  const key = useMemo(
    () =>
      Array.from(
        new Set(tickers.map((t) => t.trim().toUpperCase()).filter(Boolean))
      )
        .sort()
        .join(','),
    [tickers]
  );
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});

  useEffect(() => {
    // A changed ticker list (e.g. switching owner tab) keeps the quotes it
    // has until the immediate re-poll lands, so live totals don't snap back
    // to stored values in between; quotes for dropped tickers are unused.
    if (!key) {
      setQuotes({});
      return;
    }
    const symbols = key.split(',');
    let controller: AbortController | null = null;

    const poll = () => {
      if (isHidden()) return;
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const batches: string[][] = [];
      for (let i = 0; i < symbols.length; i += LIVE_QUOTE_BATCH_SIZE) {
        batches.push(symbols.slice(i, i + LIVE_QUOTE_BATCH_SIZE));
      }
      Promise.all(batches.map((batch) => getLiveQuotes(batch, current.signal)))
        .then((responses) => {
          if (current.signal.aborted) return;
          setQuotes(
            Object.assign({}, ...responses.map((res) => res.quotes ?? {}))
          );
        })
        .catch((err: unknown) => {
          if (current.signal.aborted) return;
          console.warn('Live quote poll failed', err);
        });
    };

    poll();
    const id = setInterval(poll, pollMs);
    const onVisible = () => {
      if (!isHidden()) poll();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      controller?.abort();
    };
  }, [key, pollMs]);

  return quotes;
}
