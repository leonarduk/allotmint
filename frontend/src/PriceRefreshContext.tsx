import { createContext, useContext, useState, type ReactNode } from "react";

interface PriceRefreshContextValue {
  lastRefresh: string | null;
  setLastRefresh: (ts: string | null) => void;
}

const defaultValue: PriceRefreshContextValue = {
  lastRefresh: null,
  setLastRefresh: () => {},
};

export const PriceRefreshContext = createContext<PriceRefreshContextValue>(defaultValue);

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
