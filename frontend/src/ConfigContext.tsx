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
  /**
   * Tabs that should be hidden/disabled from the UI.  We keep the type
   * flexible here so that the context can be consumed without depending on
   * the `Mode` union defined in `App.tsx`.
   */
  disabledTabs?: string[];
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

const ConfigContext = createContext<AppConfig>({
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: defaultTabs,
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({
    relativeViewEnabled: false,
    disabledTabs: [],
    tabs: defaultTabs,
  });

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        const tabs = { ...defaultTabs, ...((cfg as any).tabs ?? {}) };
        const disabledTabs = new Set<string>(
          Array.isArray((cfg as any).disabled_tabs)
            ? ((cfg as any).disabled_tabs as string[])
            : [],
        );
        for (const [tab, enabled] of Object.entries(tabs)) {
          if (!enabled) disabledTabs.add(tab);
        }
        setConfig({
          relativeViewEnabled: Boolean((cfg as any).relative_view_enabled),
          disabledTabs: Array.from(disabledTabs),
          tabs,
        });
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}

export { ConfigContext };

