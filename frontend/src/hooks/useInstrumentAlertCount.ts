import { useEffect, useState } from 'react';
import { getPriceTriggers } from '../api';
import type { PriceTrigger } from '../api';
import { useAlertIdentity } from './useAlertIdentity';

/** The triggers that watch `ticker` (case-insensitive, as the backend stores them upper-cased). */
export function triggersForTicker(
  triggers: PriceTrigger[],
  ticker: string
): PriceTrigger[] {
  const key = ticker.toUpperCase();
  return triggers.filter((tr) => tr.ticker.toUpperCase() === key);
}

/**
 * How many price alerts the current alert identity has on `ticker`, so the
 * research page can show it on the alerts tab before that tab is opened.
 * `count` is null until known (identity resolving, no identity/ticker, or the
 * fetch failed). `setCount` lets the open alerts panel keep it current after
 * adds and deletes without a second fetch.
 */
export function useInstrumentAlertCount(ticker: string) {
  const { identity, resolving } = useAlertIdentity();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    setCount(null);
    if (resolving || !identity || !ticker) return;
    let cancelled = false;
    getPriceTriggers(identity)
      .then((rows) => {
        if (!cancelled) setCount(triggersForTicker(rows, ticker).length);
      })
      .catch((err) => {
        // The count is a hint on a tab label; the alerts tab itself reports
        // load failures, so log rather than surface a second error here.
        if (!cancelled) console.warn('Could not load price alert count:', err);
      });
    return () => {
      cancelled = true;
    };
  }, [identity, resolving, ticker]);

  return { count, setCount };
}
