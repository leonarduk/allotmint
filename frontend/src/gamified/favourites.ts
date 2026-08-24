/**
 * Per-viewer "favourite crop" marks.
 *
 * These are a local convenience, not portfolio data: they live in this
 * browser's localStorage, never reach the backend, and are namespaced per
 * grower so two people sharing a device do not see each other's marks.
 * Every access is guarded because localStorage throws outright in some
 * contexts (private windows, blocked site data).
 */

const KEY_PREFIX = 'allotmint:plot:favourites:';

function storageKey(owner: string): string {
  return `${KEY_PREFIX}${owner || 'default'}`;
}

export function loadFavourites(owner: string): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.localStorage.getItem(storageKey(owner));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? new Set(
          parsed.filter((entry): entry is string => typeof entry === 'string')
        )
      : new Set();
  } catch {
    return new Set();
  }
}

export function saveFavourites(owner: string, favourites: Set<string>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      storageKey(owner),
      JSON.stringify([...favourites])
    );
  } catch {
    // Storage being unavailable only costs the convenience, so the toggle
    // still works for the rest of this session.
  }
}

export function toggleFavourite(
  favourites: Set<string>,
  ticker: string
): Set<string> {
  const next = new Set(favourites);
  if (next.has(ticker)) {
    next.delete(ticker);
  } else {
    next.add(ticker);
  }
  return next;
}

/** Case-insensitive match across ticker, name, bed and sector. */
export function matchesSearch(
  fields: readonly string[],
  query: string
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return fields.some((field) => field.toLowerCase().includes(needle));
}
