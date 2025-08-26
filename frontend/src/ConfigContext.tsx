/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { getConfig } from "./api";
import { tabPlugins } from "./tabPlugins";

export interface TabsConfig {
  [key: string]: boolean;
  group: boolean;
  owner: boolean;
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  timeseries: boolean;
  watchlist: boolean;
  movers: boolean;
  dataadmin: boolean;
  virtual: boolean;
  support: boolean;
  reports: boolean;
  scenario: boolean;
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
  // backend may return entries for plugins unknown to the frontend
  tabs?: Record<string, unknown>;
  disabled_tabs?: string[];
  theme?: string;
}

// build a default tabs object from the registered tab plugins
const defaultTabs = Object.fromEntries(
  tabPlugins.map((p) => [p.id, false]),
) as TabsConfig;

export interface ConfigContextValue extends AppConfig {
  refreshConfig: () => Promise<void>;
}

export const configContext = createContext<ConfigContextValue>({
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: defaultTabs,
  theme: "system",
  refreshConfig: async () => {},
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({
    relativeViewEnabled: false,
    disabledTabs: [],
    tabs: defaultTabs,
    theme: "system",
  });

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await getConfig<RawConfig>();
      const rawTabs =
        cfg && cfg.tabs && typeof cfg.tabs === "object" && !Array.isArray(cfg.tabs)
          ? (cfg.tabs as Record<string, unknown>)
          : {};
      const tabs = Object.fromEntries(
        tabPlugins.map((p) => [p.id, Boolean(rawTabs[p.id])]),
      ) as TabsConfig;
      const disabledTabs = new Set<string>(
        Array.isArray(cfg.disabled_tabs) ? cfg.disabled_tabs : [],
      );
      for (const [tab, enabled] of Object.entries(tabs)) {
        if (!enabled) disabledTabs.add(tab);
      }
      const theme = isTheme(cfg.theme) ? cfg.theme : "system";
      setConfig({
        relativeViewEnabled: Boolean(cfg.relative_view_enabled),
        disabledTabs: Array.from(disabledTabs),
        tabs,
        theme,
      });
      applyTheme(theme);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshConfig();
  }, [refreshConfig]);

  useEffect(() => {
    applyTheme(config.theme);
  }, [config.theme]);

  return (
    <configContext.Provider value={{ ...config, refreshConfig }}>
      {children}
    </configContext.Provider>
  );
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

