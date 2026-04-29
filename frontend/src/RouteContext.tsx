import { createContext, type ReactNode } from 'react';
import { useRouteMode } from './hooks/useRouteMode';
import type { Mode } from './modes';

interface RouteContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (s: string) => void;
  selectedGroup: string;
  setSelectedGroup: (s: string) => void;
}

export const RouteContext = createContext<RouteContextValue | undefined>(undefined);

export function RouteProvider({ children }: { children: ReactNode }) {
  const value = useRouteMode();
  return <RouteContext.Provider value={value}>{children}</RouteContext.Provider>;
}

// Re-export hook for backward compatibility.
export { useRoute } from './hooks/useRoute';
