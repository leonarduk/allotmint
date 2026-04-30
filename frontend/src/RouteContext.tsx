import { type ReactNode } from 'react';
import { useRouteMode } from './hooks/useRouteMode';
import { RouteContext } from './contexts/route';

export type { RouteContextValue } from './contexts/route';
export { RouteContext } from './contexts/route';

export function RouteProvider({ children }: { children: ReactNode }) {
  const value = useRouteMode();
  return <RouteContext.Provider value={value}>{children}</RouteContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export { useRoute } from './hooks/useRoute';
