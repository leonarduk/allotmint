/**
 * Pure state logic for the optional in-app workspace tabs (#10576).
 *
 * Each tab is just a remembered location (pathname + search). The URL stays
 * the source of truth: the active tab follows whatever the router shows, and
 * selecting a tab navigates to its stored path. Nothing here touches React.
 */

export interface WorkspaceTab {
  id: string;
  path: string;
}

export interface WorkspaceTabsState {
  tabs: WorkspaceTab[];
  activeId: string;
}

/** Enough to hold a group view and a handful of instruments side by side. */
export const MAX_WORKSPACE_TABS = 12;

const TABS_STORAGE_KEY = 'allotmint.workspaceTabs';
const ENABLED_STORAGE_KEY = 'allotmint.workspaceTabs.enabled';

export function createInitialState(path: string): WorkspaceTabsState {
  return { tabs: [{ id: 't1', path }], activeId: 't1' };
}

function nextId(tabs: WorkspaceTab[]): string {
  const max = tabs.reduce((acc, tab) => {
    const n = Number(tab.id.slice(1));
    return Number.isFinite(n) && n > acc ? n : acc;
  }, 0);
  return `t${max + 1}`;
}

export function activeTab(state: WorkspaceTabsState): WorkspaceTab {
  return state.tabs.find((tab) => tab.id === state.activeId) ?? state.tabs[0];
}

/** Point the active tab at `path`; returns the same object when unchanged. */
export function syncActivePath(
  state: WorkspaceTabsState,
  path: string
): WorkspaceTabsState {
  const current = activeTab(state);
  if (current.path === path) return state;
  return {
    ...state,
    tabs: state.tabs.map((tab) =>
      tab.id === current.id ? { ...tab, path } : tab
    ),
  };
}

/** Open `path` in a new tab just right of the active one and activate it. */
export function openTab(
  state: WorkspaceTabsState,
  path: string
): WorkspaceTabsState {
  if (state.tabs.length >= MAX_WORKSPACE_TABS) return state;
  const tab = { id: nextId(state.tabs), path };
  const index = state.tabs.findIndex((t) => t.id === state.activeId);
  const tabs = [...state.tabs];
  tabs.splice(index + 1, 0, tab);
  return { tabs, activeId: tab.id };
}

export function selectTab(
  state: WorkspaceTabsState,
  id: string
): WorkspaceTabsState {
  if (id === state.activeId || !state.tabs.some((tab) => tab.id === id)) {
    return state;
  }
  return { ...state, activeId: id };
}

/**
 * Close tab `id`. The last remaining tab can't be closed. Closing the active
 * tab activates its right-hand neighbour, else its left-hand one.
 */
export function closeTab(
  state: WorkspaceTabsState,
  id: string
): WorkspaceTabsState {
  const index = state.tabs.findIndex((tab) => tab.id === id);
  if (index === -1 || state.tabs.length <= 1) return state;
  const tabs = state.tabs.filter((tab) => tab.id !== id);
  if (id !== state.activeId) return { ...state, tabs };
  const neighbour = tabs[Math.min(index, tabs.length - 1)];
  return { tabs, activeId: neighbour.id };
}

function isValidState(value: unknown): value is WorkspaceTabsState {
  if (!value || typeof value !== 'object') return false;
  const { tabs, activeId } = value as Partial<WorkspaceTabsState>;
  return (
    Array.isArray(tabs) &&
    tabs.length > 0 &&
    tabs.length <= MAX_WORKSPACE_TABS &&
    tabs.every(
      (tab) =>
        tab &&
        typeof tab.id === 'string' &&
        typeof tab.path === 'string' &&
        tab.path.startsWith('/')
    ) &&
    typeof activeId === 'string' &&
    tabs.some((tab) => tab.id === activeId)
  );
}

/**
 * Tabs live in sessionStorage: they survive a reload but not closing the
 * browser tab, matching how a browser restores its own tab strip.
 */
export function loadTabsState(fallbackPath: string): WorkspaceTabsState {
  try {
    const raw = window.sessionStorage.getItem(TABS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (isValidState(parsed)) return parsed;
  } catch (err) {
    console.warn('Ignoring unreadable workspace tabs state', err);
  }
  return createInitialState(fallbackPath);
}

export function saveTabsState(state: WorkspaceTabsState): void {
  try {
    window.sessionStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    console.warn('Could not persist workspace tabs', err);
  }
}

/** The on/off preference is per browser, so it lives in localStorage. */
export function loadTabsEnabled(): boolean {
  try {
    return window.localStorage.getItem(ENABLED_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function saveTabsEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(ENABLED_STORAGE_KEY, String(enabled));
  } catch (err) {
    console.warn('Could not persist workspace tabs preference', err);
  }
}

export type WorkspaceTabLabel =
  | { kind: 'instrument'; ticker: string }
  | { kind: 'group'; group: string | null }
  | { kind: 'page'; pathname: string };

/** What a tab shows; the tab bar turns this into translated text. */
export function describeTabPath(path: string): WorkspaceTabLabel {
  const url = new URL(path, 'http://workspace.local');
  const research = url.pathname.match(/^\/research\/([^/]+)/);
  if (research) {
    return { kind: 'instrument', ticker: decodeURIComponent(research[1]) };
  }
  if (url.pathname === '/') {
    return { kind: 'group', group: url.searchParams.get('group') };
  }
  return { kind: 'page', pathname: url.pathname };
}
