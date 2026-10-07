import { useCallback, useMemo, useSyncExternalStore } from "react";

/**
 * One watchlist, stored in localStorage, shared by the Watchlist tab and the
 * add/remove toggles on the Signals and Screen tabs of the Ideas page.
 * A missing key means "never edited", which shows the default list -- so the
 * first toggle elsewhere adds to the defaults rather than replacing them.
 */
export const WATCHLIST_STORAGE_KEY = "watchlistSymbols";
export const DEFAULT_WATCHLIST_SYMBOLS =
  "^FTSE,^NDX,^GSPC,^RUT,^NYA,^VIX,^GDAXI,^N225,USDGBP=X,EURGBP=X,BTC-USD,GC=F,SI=F,VUSA.L,IWDA.AS";

const CHANGE_EVENT = "allotmint:watchlist-change";

export function parseWatchlist(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function readWatchlistRaw(): string {
  return localStorage.getItem(WATCHLIST_STORAGE_KEY) ?? DEFAULT_WATCHLIST_SYMBOLS;
}

export function writeWatchlist(symbols: string[]): void {
  localStorage.setItem(WATCHLIST_STORAGE_KEY, symbols.join(","));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Live watchlist membership plus a toggle, for per-row add/remove buttons. */
export function useWatchlist() {
  const raw = useSyncExternalStore(subscribe, readWatchlistRaw);
  const symbols = useMemo(() => parseWatchlist(raw), [raw]);
  const has = useCallback(
    (ticker: string) => {
      const target = ticker.toUpperCase();
      return symbols.some((s) => s.toUpperCase() === target);
    },
    [symbols],
  );
  const toggle = useCallback((ticker: string) => {
    const target = ticker.toUpperCase();
    const current = parseWatchlist(readWatchlistRaw());
    const present = current.some((s) => s.toUpperCase() === target);
    writeWatchlist(
      present
        ? current.filter((s) => s.toUpperCase() !== target)
        : [...current, ticker],
    );
  }, []);
  return { symbols, has, toggle };
}
