import { createContext, useContext } from 'react';
import type { WorkspaceTab } from '../lib/workspaceTabs';

export interface WorkspaceTabsContextValue {
  /** Whether the user has switched workspace tabs on (#10576). Off by default. */
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  tabs: WorkspaceTab[];
  activeId: string;
  /** Opens a new tab at the current location (a "duplicate" of the active one). */
  openCurrentInNewTab: () => void;
  selectTab: (id: string) => void;
  closeTab: (id: string) => void;
  /** Drops cached API results and remounts the active page so it refetches. */
  refreshActive: () => void;
  /** Bumped by refreshActive; the routed content is keyed on it. */
  refreshNonce: number;
}

// No provider (e.g. tests that render a page directly) behaves as "off".
export const WorkspaceTabsContext = createContext<WorkspaceTabsContextValue>({
  enabled: false,
  setEnabled: () => {},
  tabs: [],
  activeId: '',
  openCurrentInNewTab: () => {},
  selectTab: () => {},
  closeTab: () => {},
  refreshActive: () => {},
  refreshNonce: 0,
});

export const useWorkspaceTabs = () => useContext(WorkspaceTabsContext);
