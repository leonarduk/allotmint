import { type ReactNode } from 'react';
import { useRouteMode } from './hooks/useRouteMode';
import { RouteContext } from './contexts/route';

export type { RouteContextValue } from './contexts/route';
// eslint-disable-next-line react-refresh/only-export-components
export { RouteContext } from './contexts/route';

export function RouteProvider({ children }: { children: ReactNode }) {
  const value = useRouteMode();
  return <RouteContext.Provider value={value}>{children}</RouteContext.Provider>;
}

export { useRoute } from './hooks/useRoute';
