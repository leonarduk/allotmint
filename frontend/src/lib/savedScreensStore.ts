import { useMemo, useSyncExternalStore } from 'react';

/**
 * Named screener screens (watchlist + tickers + filter values), stored in
 * localStorage so a user can save, update, rename and delete their own
 * screens on the Screen tab of the Ideas page.
 */
export const SAVED_SCREENS_STORAGE_KEY = 'screenerSavedScreens';

export interface SavedScreen {
  name: string;
  watchlist: string;
  tickers: string;
  filters: Record<string, string>;
}

const CHANGE_EVENT = 'allotmint:saved-screens-change';

function isSavedScreen(value: unknown): value is SavedScreen {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === 'string' &&
    typeof v.watchlist === 'string' &&
    typeof v.tickers === 'string' &&
    !!v.filters &&
    typeof v.filters === 'object'
  );
}

export function parseSavedScreens(raw: string | null): SavedScreen[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isSavedScreen) : [];
  } catch (err) {
    console.warn('Ignoring unreadable saved screener screens:', err);
    return [];
  }
}

function readRaw(): string | null {
  return localStorage.getItem(SAVED_SCREENS_STORAGE_KEY);
}

export function readSavedScreens(): SavedScreen[] {
  return parseSavedScreens(readRaw());
}

function writeSavedScreens(screens: SavedScreen[]): void {
  localStorage.setItem(SAVED_SCREENS_STORAGE_KEY, JSON.stringify(screens));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function sameName(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/** Insert or overwrite (case-insensitive name match) a screen. */
export function saveScreen(screen: SavedScreen): void {
  const name = screen.name.trim();
  const rest = readSavedScreens().filter((s) => !sameName(s.name, name));
  writeSavedScreens(
    [...rest, { ...screen, name }].sort((a, b) => a.name.localeCompare(b.name))
  );
}

/** Rename a screen; returns false if the target name is taken by another. */
export function renameScreen(from: string, to: string): boolean {
  const target = to.trim();
  const screens = readSavedScreens();
  if (
    !sameName(from, target) &&
    screens.some((s) => sameName(s.name, target))
  ) {
    return false;
  }
  writeSavedScreens(
    screens
      .map((s) => (sameName(s.name, from) ? { ...s, name: target } : s))
      .sort((a, b) => a.name.localeCompare(b.name))
  );
  return true;
}

export function deleteScreen(name: string): void {
  writeSavedScreens(readSavedScreens().filter((s) => !sameName(s.name, name)));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

/** Live list of saved screens, re-rendering on changes from any tab. */
export function useSavedScreens(): SavedScreen[] {
  const raw = useSyncExternalStore(subscribe, readRaw);
  return useMemo(() => parseSavedScreens(raw), [raw]);
}
