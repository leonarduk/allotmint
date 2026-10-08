import { useEffect, useState } from 'react';
import { getInstrumentNotes } from '../api';
import { useAlertIdentity } from './useAlertIdentity';

/**
 * How many research notes the current identity has on `ticker`, so the
 * research page can show it on the notes tab before that tab is opened.
 * `count` is null until known. `setCount` lets the open notes panel keep it
 * current after adds and deletes without a second fetch.
 */
export function useInstrumentNoteCount(ticker: string) {
  const { identity, resolving } = useAlertIdentity();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    setCount(null);
    if (resolving || !identity || !ticker) return;
    let cancelled = false;
    getInstrumentNotes(identity, ticker)
      .then((rows) => {
        if (!cancelled) setCount(rows.length);
      })
      .catch((err) => {
        // The count is a hint on a tab label; the notes tab itself reports
        // load failures, so log rather than surface a second error here.
        if (!cancelled)
          console.warn('Could not load research note count:', err);
      });
    return () => {
      cancelled = true;
    };
  }, [identity, resolving, ticker]);

  return { count, setCount };
}
