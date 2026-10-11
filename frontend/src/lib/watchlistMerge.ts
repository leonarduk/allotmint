import type { NamedWatchlist, WatchlistsState } from "./watchlistStore";

// Merging two copies of a user's watchlists without losing either side's
// edits (#10713). Pure functions; watchlistSync.ts decides when to use them.

// Mirrors MAX_LISTS / MAX_NAME_CHARS in backend/common/watchlists.py.
const MAX_LISTS = 50;
const MAX_NAME_CHARS = 100;
const BROWSER_SUFFIX = " (this browser)";

const nameKey = (name: string) => name.trim().toLowerCase();
const symbolKey = (symbol: string) => symbol.toUpperCase();

function sameContent(a: NamedWatchlist, b: NamedWatchlist): boolean {
  return a.name === b.name && a.symbols.join(",") === b.symbols.join(",");
}

function freeName(taken: Set<string>, name: string): string {
  if (!taken.has(nameKey(name))) return name;
  for (let n = 1; ; n += 1) {
    const suffix = n === 1 ? BROWSER_SUFFIX : ` (this browser ${n})`;
    const candidate = name.slice(0, MAX_NAME_CHARS - suffix.length) + suffix;
    if (!taken.has(nameKey(candidate))) return candidate;
  }
}

/** Renames later lists that clash (ignoring case) and keeps at most MAX_LISTS. */
function tidy(lists: NamedWatchlist[]): NamedWatchlist[] {
  const taken = new Set<string>();
  const out: NamedWatchlist[] = [];
  for (const list of lists) {
    if (out.length >= MAX_LISTS) {
      console.warn(`Watchlist "${list.name}" was not kept: the ${MAX_LISTS}-list limit is reached`);
      continue;
    }
    const name = freeName(taken, list.name);
    taken.add(nameKey(name));
    out.push(name === list.name ? list : { ...list, name });
  }
  return out;
}

function newId(): string {
  return `wl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * First sync, with no common ancestor: the saved lists plus each of this
 * browser's lists that differs from all of them, renamed on a name clash.
 * Returns `saved` itself when nothing is added.
 */
export function mergeBrowserLists(saved: WatchlistsState, browser: WatchlistsState): WatchlistsState {
  const isSaved = (b: NamedWatchlist) =>
    saved.lists.some((l) => nameKey(l.name) === nameKey(b.name) && l.symbols.join(",") === b.symbols.join(","));
  const extra = browser.lists.filter((b) => !isSaved(b)).map((b) => ({ ...b, id: newId() }));
  if (!extra.length) return saved;
  return { ...saved, lists: tidy([...saved.lists, ...extra]) };
}

/** One list edited on both sides: this side's name change wins; symbol adds and removes from both apply. */
function mergeList(base: NamedWatchlist, local: NamedWatchlist, remote: NamedWatchlist): NamedWatchlist {
  const baseKeys = new Set(base.symbols.map(symbolKey));
  const localKeys = new Set(local.symbols.map(symbolKey));
  const removed = new Set([...baseKeys].filter((k) => !localKeys.has(k)));
  const symbols = remote.symbols.filter((s) => !removed.has(symbolKey(s)));
  const have = new Set(symbols.map(symbolKey));
  for (const s of local.symbols) {
    const k = symbolKey(s);
    if (!baseKeys.has(k) && !have.has(k)) {
      symbols.push(s);
      have.add(k);
    }
  }
  return { id: remote.id, name: local.name !== base.name ? local.name : remote.name, symbols };
}

/**
 * Three-way merge by list id: `base` is the copy both sides started from,
 * `local` this browser's edits, `remote` the copy saved meanwhile elsewhere.
 * Both sides' adds, removes and renames apply; a list deleted on one side
 * stays deleted unless the other side edited it (an edit beats a delete, so
 * nothing typed is lost). Remote order first, then this browser's new lists.
 */
export function threeWayMerge(
  base: WatchlistsState,
  local: WatchlistsState,
  remote: WatchlistsState,
): WatchlistsState {
  const baseById = new Map(base.lists.map((l) => [l.id, l]));
  const localById = new Map(local.lists.map((l) => [l.id, l]));
  const remoteIds = new Set(remote.lists.map((l) => l.id));
  const lists: NamedWatchlist[] = [];
  for (const r of remote.lists) {
    const b = baseById.get(r.id);
    const l = localById.get(r.id);
    if (!b || !l) {
      // Added remotely; or deleted here, which only stands if remote left it alone.
      if (!b || !sameContent(r, b)) lists.push(r);
      continue;
    }
    lists.push(mergeList(b, l, r));
  }
  for (const l of local.lists) {
    if (remoteIds.has(l.id)) continue;
    const b = baseById.get(l.id);
    // Added here; or deleted remotely, which only stands if this side left it alone.
    if (!b || !sameContent(l, b)) lists.push(l);
  }
  const merged = tidy(lists);
  if (!merged.length) return remote;
  const wanted = local.activeId !== base.activeId ? local.activeId : remote.activeId;
  const activeId = merged.some((l) => l.id === wanted)
    ? wanted
    : merged.some((l) => l.id === remote.activeId)
      ? remote.activeId
      : merged[0].id;
  return { activeId, lists: merged };
}
