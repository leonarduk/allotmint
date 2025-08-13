import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getConfig } from "./api";

export interface TabsConfig {
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  query: boolean;
  trading: boolean;
  timeseries: boolean;
  watchlist: boolean;
  virtual: boolean;
  support: boolean;
}

export interface AppConfig {
  relativeViewEnabled: boolean;
  tabs: TabsConfig;
}

const defaultTabs: TabsConfig = {
  instrument: true,
  performance: true,
  transactions: true,
  screener: true,
  query: true,
  trading: true,
  timeseries: true,
  watchlist: true,
  virtual: true,
  support: true,
};

export const ConfigContext = createContext<AppConfig>({
  relativeViewEnabled: false,
  tabs: defaultTabs,
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({
    relativeViewEnabled: false,
    tabs: defaultTabs,
  });

  useEffect(() => {
    getConfig()
      .then((cfg) =>
        setConfig({
          relativeViewEnabled: Boolean((cfg as any).relative_view_enabled),
          tabs: { ...defaultTabs, ...((cfg as any).tabs ?? {}) },
        })
      )
      .catch(() => {
        /* ignore */
      });
  }, []);

  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}

