import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  findWatchlist,
  setActiveWatchlist,
  useWatchlists,
} from '../lib/watchlistStore';

export const WATCHLIST_URL_PARAM = 'list';

/**
 * Keep the active watchlist and `?list=<name>` in step so a list can be
 * bookmarked. A param that changed since we last saw it (first load, a
 * bookmark, a hand-edited URL) selects that list; otherwise the URL follows
 * the active list, including renames. URL rewrites use `replace` so
 * switching lists doesn't pile up history entries.
 *
 * Returns the requested name when no list matches it, so the page can say
 * why it is showing a different list.
 */
export function useWatchlistUrlParam(): string | null {
  const { state, active } = useWatchlists();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get(WATCHLIST_URL_PARAM);
  const lastSeen = useRef<string | null>(null);
  const [missing, setMissing] = useState<{
    ref: string;
    shownId: string;
  } | null>(null);

  useEffect(() => {
    if (requested !== null && requested !== lastSeen.current) {
      lastSeen.current = requested;
      const target = findWatchlist(state, requested);
      if (!target) {
        setMissing({ ref: requested, shownId: active.id });
      } else if (target.id !== active.id) {
        setMissing(null);
        setActiveWatchlist(target.id);
        return; // the URL is re-synced once the switch re-renders
      }
    }
    if (requested !== active.name) {
      lastSeen.current = active.name;
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set(WATCHLIST_URL_PARAM, active.name);
          return next;
        },
        { replace: true }
      );
    }
  }, [requested, state, active.id, active.name, setSearchParams]);

  // Only explain the fallback while the fallback list is still on screen:
  // the URL is rewritten to that list straight away (with lastSeen updated
  // first, so the rewrite isn't mistaken for a new request), but the notice
  // stays until the user picks another list.
  return missing && missing.shownId === active.id ? missing.ref : null;
}
