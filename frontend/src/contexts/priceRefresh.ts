import { createContext } from 'react';

export interface PriceRefreshContextValue {
  lastRefresh: string | null;
  setLastRefresh: (ts: string | null) => void;
}

const defaultValue: PriceRefreshContextValue = {
  lastRefresh: null,
  setLastRefresh: () => {},
};

export const PriceRefreshContext =
  createContext<PriceRefreshContextValue>(defaultValue);
