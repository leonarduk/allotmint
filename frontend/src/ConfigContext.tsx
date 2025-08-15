/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getConfig } from "./api";

export interface TabsConfig {
  [key: string]: boolean;
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  query: boolean;
  trading: boolean;
  timeseries: boolean;
  groupInstrumentMemberTimeseries: boolean;
  watchlist: boolean;
  movers: boolean;
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
  theme: "dark" | "light" | "system";
}

const defaultTabs: TabsConfig = {
  instrument: true,
  performance: true,
  transactions: true,
  screener: true,
  query: true,
  trading: true,
  timeseries: true,
  groupInstrumentMemberTimeseries: true,
  watchlist: true,
  movers: true,
  virtual: true,
  support: true,
};

export const configContext = createContext<AppConfig>({
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: defaultTabs,
  theme: "system",
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({
    relativeViewEnabled: false,
    disabledTabs: [],
    tabs: defaultTabs,
    theme: "system",
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
        const theme =
          typeof (cfg as any).theme === "string" ? ((cfg as any).theme as any) : "system";
        setConfig({
          relativeViewEnabled: Boolean((cfg as any).relative_view_enabled),
          disabledTabs: Array.from(disabledTabs),
          tabs,
          theme,
        });
        applyTheme(theme);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  useEffect(() => {
    applyTheme(config.theme);
  }, [config.theme]);

  return <configContext.Provider value={config}>{children}</configContext.Provider>;
}

export function useConfig() {
  return useContext(configContext);
}

function applyTheme(theme: string) {
  const root = document.documentElement;
  if (!root) return;
  if (theme === "dark" || theme === "light") {
    root.setAttribute("data-theme", theme);
  } else {
    root.removeAttribute("data-theme");
  }
}

