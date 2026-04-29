import { useState, useContext, type ReactNode } from 'react';
import { PriceRefreshContext } from './contexts/priceRefresh';

export type { PriceRefreshContextValue } from './contexts/priceRefresh';
export { PriceRefreshContext } from './contexts/priceRefresh';

export function PriceRefreshProvider({ children }: { children: ReactNode }) {
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  return (
    <PriceRefreshContext.Provider value={{ lastRefresh, setLastRefresh }}>
      {children}
    </PriceRefreshContext.Provider>
  );
}

export function usePriceRefresh() {
  return useContext(PriceRefreshContext);
}
