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

export interface TabsConfig {
  [key: string]: boolean;
  group: boolean;
  owner: boolean;
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  trading: boolean;
  timeseries: boolean;
  watchlist: boolean;
  movers: boolean;
  instrumentadmin: boolean;
  dataadmin: boolean;
  virtual: boolean;
  support: boolean;
  settings: boolean;
  profile: boolean;
  reports: boolean;
  scenario: boolean;
  logs: boolean;
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
  group: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: true,
  screener: true,
  trading: true,
  timeseries: true,
  watchlist: true,
  movers: true,
  instrumentadmin: true,
  dataadmin: true,
  virtual: true,
  support: true,
  settings: true,
  profile: false,
  reports: true,
  scenario: true,
  logs: true,
};

export interface ConfigContextValue extends AppConfig {
  refreshConfig: () => Promise<void>;
  setRelativeViewEnabled: (enabled: boolean) => void;
}

export const configContext = createContext<ConfigContextValue>({
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: defaultTabs,
  theme: "system",
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>(() => {
    const stored = localStorage.getItem("relativeViewEnabled");
    return {
      relativeViewEnabled: stored === "true",
      disabledTabs: [],
      tabs: defaultTabs,
      theme: "system",
    };
  });

  const setRelativeViewEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({ ...prev, relativeViewEnabled: enabled }));
    localStorage.setItem("relativeViewEnabled", String(enabled));
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await getConfig<RawConfig>();
      const tabs = { ...defaultTabs, ...(cfg.tabs ?? {}) } as TabsConfig;
      const disabledTabs = new Set<string>(
        Array.isArray(cfg.disabled_tabs) ? cfg.disabled_tabs : [],
      );
      for (const [tab, enabled] of Object.entries(tabs) as [
        string,
        boolean,
      ][]) {
        if (!enabled) disabledTabs.add(String(tab));
      }
      const theme = isTheme(cfg.theme) ? cfg.theme : "system";
      const stored = localStorage.getItem("relativeViewEnabled");
      setConfig({
        relativeViewEnabled: stored ? stored === "true" : Boolean(cfg.relative_view_enabled),
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
    <configContext.Provider value={{ ...config, refreshConfig, setRelativeViewEnabled }}>
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

