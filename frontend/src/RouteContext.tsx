import { createContext, useContext, type ReactNode } from "react";
import { useRouteMode } from "./hooks/useRouteMode";
import type { Mode } from "./modes";

interface RouteContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedOwner: string;
  setSelectedOwner: (s: string) => void;
  selectedGroup: string;
  setSelectedGroup: (s: string) => void;
}

const RouteContext = createContext<RouteContextValue | undefined>(undefined);

export function RouteProvider({ children }: { children: ReactNode }) {
  const value = useRouteMode();
  return <RouteContext.Provider value={value}>{children}</RouteContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRoute() {
  const ctx = useContext(RouteContext);
  if (!ctx) throw new Error("useRoute must be used within RouteProvider");
  return ctx;
}

