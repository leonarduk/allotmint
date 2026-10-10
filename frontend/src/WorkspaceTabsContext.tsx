import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { clearGroupInstrumentCache } from './api';
import {
  WorkspaceTabsContext,
  useWorkspaceTabs,
  type WorkspaceTabsContextValue,
} from './contexts/workspaceTabs';
import {
  activeTab,
  closeTab as closeTabState,
  loadTabsEnabled,
  loadTabsState,
  openTab,
  saveTabsEnabled,
  saveTabsState,
  selectTab as selectTabState,
  syncActivePath,
} from './lib/workspaceTabs';
import { CHAT_WINDOW_PATH } from './utils/chatWindow';
import { clearFetchCache } from './utils/fetchCache';

/**
 * Optional in-app workspace tabs (#10576). While enabled, the active tab
 * follows the router location and switching tabs navigates to the stored
 * path, so deep links and back/forward behave exactly as without tabs.
 */
export function WorkspaceTabsProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentPath = `${location.pathname}${location.search}`;
  const [enabled, setEnabledState] = useState(loadTabsEnabled);
  const [state, setState] = useState(() => loadTabsState(currentPath));
  const [refreshNonce, setRefreshNonce] = useState(0);
  // The detached chat window is its own browser window, not a workspace
  // view, so it never records or persists a tab location.
  const tracking = enabled && location.pathname !== CHAT_WINDOW_PATH;

  // Keyed on the location only. selectTab/closeTab call setState before
  // navigate(), so the new active tab is committed no later than the new
  // URL (same batch, or before it when the router navigates in a
  // transition) -- this never writes a tab's path into its neighbour.
  useEffect(() => {
    if (tracking) setState((s) => syncActivePath(s, currentPath));
  }, [currentPath, tracking]);

  useEffect(() => {
    if (tracking) saveTabsState(state);
  }, [tracking, state]);

  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    saveTabsEnabled(next);
  }, []);

  const goTo = useCallback(
    (path: string) => {
      if (path !== currentPath) navigate(path);
    },
    [currentPath, navigate]
  );

  const selectTab = useCallback(
    (id: string) => {
      const next = selectTabState(state, id);
      setState(next);
      goTo(activeTab(next).path);
    },
    [goTo, state]
  );

  const closeTab = useCallback(
    (id: string) => {
      const next = closeTabState(state, id);
      setState(next);
      goTo(activeTab(next).path);
    },
    [goTo, state]
  );

  const openCurrentInNewTab = useCallback(() => {
    setState((s) => openTab(s, currentPath));
  }, [currentPath]);

  const refreshActive = useCallback(() => {
    clearFetchCache();
    clearGroupInstrumentCache();
    setRefreshNonce((n) => n + 1);
  }, []);

  const value = useMemo<WorkspaceTabsContextValue>(
    () => ({
      enabled,
      setEnabled,
      tabs: state.tabs,
      activeId: state.activeId,
      openCurrentInNewTab,
      selectTab,
      closeTab,
      refreshActive,
      refreshNonce,
    }),
    [
      closeTab,
      enabled,
      openCurrentInNewTab,
      refreshActive,
      refreshNonce,
      selectTab,
      setEnabled,
      state,
    ]
  );

  return (
    <WorkspaceTabsContext.Provider value={value}>
      {children}
    </WorkspaceTabsContext.Provider>
  );
}

/** Remounts its children whenever the active tab is refreshed. */
export function RemountOnTabRefresh({ children }: { children: ReactNode }) {
  const { refreshNonce } = useWorkspaceTabs();
  return <Fragment key={refreshNonce}>{children}</Fragment>;
}
