import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";

/**
 * Named watchlists, stored in localStorage and shared by the Watchlist tab,
 * the add/remove pickers on the Signals/Screen tabs and the instrument page,
 * and the gamified seed catalogue.
 *
 * All lists live as JSON under WATCHLISTS_STORAGE_KEY together with the id
 * of the list the Watchlist tab is showing. Before multiple lists existed
 * there was one comma-separated list under LEGACY_WATCHLIST_STORAGE_KEY; while
 * the new key is absent that legacy list (or, if never edited, the default
 * list) is presented as the single "My watchlist". The legacy key is left in
 * place on first write so a rollback still finds the user's old list.
 *
 * Which list is shown is per browser tab (#10735): each tab pins its own
 * choice in sessionStorage, so switching lists in one tab doesn't switch every
 * other open Watchlist tab. The shared `activeId` is still written, and is
 * what a new tab opens on.
 *
 * localStorage is a cache: lib/watchlistSync.ts keeps it in step with the
 * signed-in user's copy on the server (#10713), told of every edit here via
 * onWatchlistsEdited and writing the server's copy back with adoptWatchlists.
 */
export const WATCHLISTS_STORAGE_KEY = "watchlists";
export const LEGACY_WATCHLIST_STORAGE_KEY = "watchlistSymbols";
export const DEFAULT_WATCHLIST_SYMBOLS =
  "^FTSE,^NDX,^GSPC,^RUT,^NYA,^VIX,^GDAXI,^N225,USDGBP=X,EURGBP=X,BTC-USD,GC=F,SI=F,VUSA.L,IWDA.AS";
export const DEFAULT_WATCHLIST_NAME = "My watchlist";
const DEFAULT_WATCHLIST_ID = "default";
export const TAB_ACTIVE_WATCHLIST_KEY = "watchlistActiveId";

const CHANGE_EVENT = "allotmint:watchlist-change";

export interface NamedWatchlist {
  id: string;
  name: string;
  symbols: string[];
}

export interface WatchlistsState {
  activeId: string;
  lists: NamedWatchlist[];
}

export function parseWatchlist(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function isNamedWatchlist(value: unknown): value is NamedWatchlist {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    typeof v.name === "string" &&
    Array.isArray(v.symbols) &&
    v.symbols.every((s) => typeof s === "string")
  );
}

function readLegacyRaw(): string | null {
  return localStorage.getItem(LEGACY_WATCHLIST_STORAGE_KEY);
}

function legacyState(legacyRaw: string | null): WatchlistsState {
  const raw = legacyRaw ?? DEFAULT_WATCHLIST_SYMBOLS;
  return {
    activeId: DEFAULT_WATCHLIST_ID,
    lists: [
      {
        id: DEFAULT_WATCHLIST_ID,
        name: DEFAULT_WATCHLIST_NAME,
        symbols: parseWatchlist(raw),
      },
    ],
  };
}

/** Parse stored state; null if absent or unreadable (falls back to legacy). */
export function parseWatchlists(raw: string | null): WatchlistsState | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const p = parsed as Record<string, unknown>;
    const lists = Array.isArray(p.lists) ? p.lists.filter(isNamedWatchlist) : [];
    if (!lists.length) return null;
    const activeId =
      typeof p.activeId === "string" && lists.some((l) => l.id === p.activeId)
        ? p.activeId
        : lists[0].id;
    return { activeId, lists };
  } catch (err) {
    console.warn("Ignoring unreadable watchlists:", err);
    return null;
  }
}

function readRaw(): string | null {
  return localStorage.getItem(WATCHLISTS_STORAGE_KEY);
}

function readTabActiveId(): string | null {
  try {
    return sessionStorage.getItem(TAB_ACTIVE_WATCHLIST_KEY);
  } catch (err) {
    console.warn("Watchlist choice for this tab unavailable:", err);
    return null;
  }
}

function pinTabActiveId(id: string): void {
  try {
    sessionStorage.setItem(TAB_ACTIVE_WATCHLIST_KEY, id);
  } catch (err) {
    console.warn("Could not remember this tab's watchlist:", err);
  }
}

function storedState(raw: string | null, legacyRaw: string | null) {
  return parseWatchlists(raw) ?? legacyState(legacyRaw);
}

/** `state` showing this tab's list; `state` itself if that changes nothing. */
function withTabActive(
  state: WatchlistsState,
  tabActiveId: string | null,
): WatchlistsState {
  return tabActiveId &&
    tabActiveId !== state.activeId &&
    state.lists.some((l) => l.id === tabActiveId)
    ? { ...state, activeId: tabActiveId }
    : state;
}

/** Every list, with `activeId` the list this tab is showing. */
export function readWatchlists(): WatchlistsState {
  return withTabActive(
    storedState(readRaw(), readLegacyRaw()),
    readTabActiveId(),
  );
}

const editListeners = new Set<() => void>();

/** Call `listener` after every edit made in this tab (not on adoptWatchlists). */
export function onWatchlistsEdited(listener: () => void): () => void {
  editListeners.add(listener);
  return () => {
    editListeners.delete(listener);
  };
}

function storeWatchlists(state: WatchlistsState): void {
  localStorage.setItem(WATCHLISTS_STORAGE_KEY, JSON.stringify(state));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function writeWatchlists(state: WatchlistsState): void {
  // Edits here start from readWatchlists(), so activeId is this tab's list.
  pinTabActiveId(state.activeId);
  storeWatchlists(state);
  editListeners.forEach((listener) => listener());
}

/** True once this browser holds lists of its own (edited, or the legacy list). */
export function hasStoredWatchlists(): boolean {
  return readRaw() !== null || readLegacyRaw() !== null;
}

/** Replace the cached lists with a copy from the server; not an edit. */
export function adoptWatchlists(state: WatchlistsState): void {
  storeWatchlists(state);
}

/** The lists a browser with nothing stored shows: the default list alone. */
export function defaultWatchlists(): WatchlistsState {
  return legacyState(null);
}

export function activeWatchlist(state: WatchlistsState): NamedWatchlist {
  return state.lists.find((l) => l.id === state.activeId) ?? state.lists[0];
}

/** Symbols of the list currently shown on the Watchlist tab. */
export function readActiveSymbols(): string[] {
  return activeWatchlist(readWatchlists()).symbols;
}

function sameName(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/**
 * Resolve a list from a bookmarkable reference: its id, else its name
 * (case-insensitive). Names are unique, so at most one list matches.
 */
export function findWatchlist(
  state: WatchlistsState,
  ref: string,
): NamedWatchlist | undefined {
  return (
    state.lists.find((l) => l.id === ref) ??
    state.lists.find((l) => sameName(l.name, ref))
  );
}

function nameTaken(state: WatchlistsState, name: string, exceptId?: string) {
  return state.lists.some((l) => l.id !== exceptId && sameName(l.name, name));
}

function newId(): string {
  return `wl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function updateList(
  id: string,
  change: (list: NamedWatchlist) => NamedWatchlist,
): void {
  const state = readWatchlists();
  writeWatchlists({
    ...state,
    lists: state.lists.map((l) => (l.id === id ? change(l) : l)),
  });
}

export function setActiveWatchlist(id: string): void {
  const state = readWatchlists();
  if (!state.lists.some((l) => l.id === id)) return;
  writeWatchlists({ ...state, activeId: id });
}

/**
 * Create a list (optionally pre-filled) and make it active.
 * Returns the new id, or null if the name is blank or already used.
 */
export function createWatchlist(
  name: string,
  symbols: string[] = [],
): string | null {
  const trimmed = name.trim();
  const state = readWatchlists();
  if (!trimmed || nameTaken(state, trimmed)) return null;
  const id = newId();
  writeWatchlists({
    activeId: id,
    lists: [...state.lists, { id, name: trimmed, symbols: [...symbols] }],
  });
  return id;
}

/** Copy a list under a new name and make the copy active; null if refused. */
export function copyWatchlist(id: string, name: string): string | null {
  const source = readWatchlists().lists.find((l) => l.id === id);
  return source ? createWatchlist(name, source.symbols) : null;
}

/** Rename a list; false if the name is blank or used by another list. */
export function renameWatchlist(id: string, name: string): boolean {
  const trimmed = name.trim();
  const state = readWatchlists();
  if (!trimmed || nameTaken(state, trimmed, id)) return false;
  updateList(id, (l) => ({ ...l, name: trimmed }));
  return true;
}

/** Delete a list; refuses to delete the last one so there's always a list. */
export function deleteWatchlist(id: string): boolean {
  const state = readWatchlists();
  const lists = state.lists.filter((l) => l.id !== id);
  if (!lists.length || lists.length === state.lists.length) return false;
  const activeId = state.activeId === id ? lists[0].id : state.activeId;
  writeWatchlists({ activeId, lists });
  return true;
}

export function setWatchlistSymbols(id: string, symbols: string[]): void {
  updateList(id, (l) => ({ ...l, symbols: [...symbols] }));
}

function containsTicker(symbols: string[], ticker: string): boolean {
  const target = ticker.toUpperCase();
  return symbols.some((s) => s.toUpperCase() === target);
}

/** Add or remove (case-insensitively) a ticker on one list. */
export function toggleInWatchlist(id: string, ticker: string): void {
  const target = ticker.toUpperCase();
  updateList(id, (l) => ({
    ...l,
    symbols: containsTicker(l.symbols, ticker)
      ? l.symbols.filter((s) => s.toUpperCase() !== target)
      : [...l.symbols, ticker],
  }));
}

export function suggestCopyName(state: WatchlistsState, name: string): string {
  let candidate = `${name} (copy)`;
  for (let n = 2; nameTaken(state, candidate); n += 1) {
    candidate = `${name} (copy ${n})`;
  }
  return candidate;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Live view of every watchlist, re-rendering on changes from any tab. */
export function useWatchlists() {
  const raw = useSyncExternalStore(subscribe, readRaw);
  const legacyRaw = useSyncExternalStore(subscribe, readLegacyRaw);
  const tabActiveId = useSyncExternalStore(subscribe, readTabActiveId);
  const stored = useMemo(() => storedState(raw, legacyRaw), [raw, legacyRaw]);
  const state = useMemo(
    () => withTabActive(stored, tabActiveId),
    [stored, tabActiveId],
  );
  // Pin the list this tab opened on, so another tab switching lists later
  // (which rewrites the shared activeId) doesn't switch this one too.
  useEffect(() => {
    if (readTabActiveId() === null) pinTabActiveId(state.activeId);
  }, [state.activeId]);
  const active = activeWatchlist(state);
  /** Lists containing the ticker (case-insensitive). */
  const listsWith = useCallback(
    (ticker: string) =>
      state.lists.filter((l) => containsTicker(l.symbols, ticker)),
    [state],
  );
  return { state, lists: state.lists, active, listsWith };
}
