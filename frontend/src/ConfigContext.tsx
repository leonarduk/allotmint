/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getConfig } from "./api";

export interface TabsConfig {
  [key: string]: boolean;
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  timeseries: boolean;
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

export interface RawConfig {
  relative_view_enabled?: boolean;
  tabs?: Partial<TabsConfig>;
  disabled_tabs?: string[];
  theme?: string;
}

const defaultTabs: TabsConfig = {
  instrument: true,
  performance: true,
  transactions: true,
  screener: true,
  timeseries: true,
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
    getConfig<RawConfig>()
      .then((cfg) => {
        const tabs: TabsConfig = { ...defaultTabs, ...(cfg.tabs ?? {}) };
        const disabledTabs = new Set<string>(
          Array.isArray(cfg.disabled_tabs) ? cfg.disabled_tabs : [],
        );
        for (const [tab, enabled] of Object.entries(tabs) as [string, boolean][]) {
          if (!enabled) disabledTabs.add(String(tab));
        }
        const theme = isTheme(cfg.theme) ? cfg.theme : "system";
        setConfig({
          relativeViewEnabled: Boolean(cfg.relative_view_enabled),
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

function isTheme(value: unknown): value is AppConfig["theme"] {
  return value === "dark" || value === "light" || value === "system";
}

function applyTheme(theme: AppConfig["theme"]) {
  const root = document.documentElement;
  if (!root) return;
  if (theme === "dark" || theme === "light") {
    root.setAttribute("data-theme", theme);
  } else {
    root.removeAttribute("data-theme");
  }
}

