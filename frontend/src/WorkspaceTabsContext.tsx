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

  // Keyed on the location only: selectTab updates `state` and navigates in
  // the same batch, so this never sees the new active tab with the old URL.
  useEffect(() => {
    if (enabled) setState((s) => syncActivePath(s, currentPath));
  }, [currentPath, enabled]);

  useEffect(() => {
    if (enabled) saveTabsState(state);
  }, [enabled, state]);

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
