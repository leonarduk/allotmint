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
  market: boolean;
  owner: boolean;
  instrument: boolean;
  performance: boolean;
  transactions: boolean;
  screener: boolean;
  trading: boolean;
  timeseries: boolean;
  watchlist: boolean;
  allocation: boolean;
  rebalance: boolean;
  movers: boolean;
  instrumentadmin: boolean;
  dataadmin: boolean;
  virtual: boolean;
  research: boolean;
  support: boolean;
  settings: boolean;
  profile: boolean;
  alerts: boolean;
  pension: boolean;
  trail: boolean;
  alertsettings: boolean;
  taxtools: boolean;
  'trade-compliance': boolean;
  reports: boolean;
  scenario: boolean;
}

export interface AppConfig {
  relativeViewEnabled: boolean;
  familyMvpEnabled: boolean;
  /**
   * Tabs that should be hidden/disabled from the UI.  We keep the type
   * flexible here so that the context can be consumed without depending on
   * the `Mode` union defined in `App.tsx`.
   */
  disabledTabs?: string[];
  tabs: TabsConfig;
  theme: "dark" | "light" | "system";
  baseCurrency: string;
  enableAdvancedAnalytics?: boolean;
}

export interface RawConfig {
  relative_view_enabled?: boolean | null;
  tabs?: Partial<TabsConfig>;
  disabled_tabs?: string[];
  enable_family_mvp?: boolean;
  enable_compliance_workflows?: boolean;
  enable_advanced_analytics?: boolean;
  enable_reporting_extended?: boolean;
  theme?: string | null;
  allowed_emails?: string[] | null;
}

const defaultTabs: TabsConfig = {
  group: true,
  market: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: true,
  screener: true,
  trading: true,
  timeseries: true,
  watchlist: true,
  allocation: true,
  rebalance: true,
  movers: true,
  instrumentadmin: true,
  dataadmin: true,
  virtual: true,
  research: true,
  support: true,
  settings: true,
  profile: false,
  alerts: true,
  pension: true,
  trail: false,
  alertsettings: true,
  taxtools: false,
  'trade-compliance': false,
  reports: false,
  scenario: true,
};

export interface ConfigContextValue extends AppConfig {
  refreshConfig: () => Promise<void>;
  setRelativeViewEnabled: (enabled: boolean) => void;
  setBaseCurrency: (currency: string) => void;
}

export const configContext = createContext<ConfigContextValue>({
  relativeViewEnabled: false,
  familyMvpEnabled: true,
  disabledTabs: [],
  tabs: defaultTabs,
  theme: "system",
  baseCurrency: "GBP",
  enableAdvancedAnalytics: true,
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>(() => {
    const storedRel =
      typeof window !== "undefined"
        ? window.localStorage.getItem("relativeViewEnabled")
        : null;
    const storedCurrency =
      typeof window !== "undefined"
        ? window.localStorage.getItem("baseCurrency")
        : null;
    return {
      relativeViewEnabled: storedRel === "true",
      familyMvpEnabled: true,
      disabledTabs: [],
      tabs: defaultTabs,
      theme: "system",
      baseCurrency: storedCurrency || "GBP",
      enableAdvancedAnalytics: true,
    };
  });
  const setRelativeViewEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({ ...prev, relativeViewEnabled: enabled }));
    if (typeof window !== "undefined") {
      window.localStorage.setItem("relativeViewEnabled", String(enabled));
    }
  }, []);

  const setBaseCurrency = useCallback((currency: string) => {
    setConfig((prev) => ({ ...prev, baseCurrency: currency }));
    if (typeof window !== "undefined") {
      window.localStorage.setItem("baseCurrency", currency);
    }
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await getConfig<RawConfig>();
      const tabs: TabsConfig = { ...defaultTabs };
      if (cfg.tabs && typeof cfg.tabs === "object") {
        for (const [tab, value] of Object.entries(cfg.tabs)) {
          if (typeof value === "boolean") {
            (tabs as Record<string, boolean>)[tab] = value;
          }
        }
      }
      const disabledTabs = new Set<string>(
        Array.isArray(cfg.disabled_tabs) ? cfg.disabled_tabs : [],
      );
      const disableTab = (tab: keyof TabsConfig) => {
        disabledTabs.add(tab);
        tabs[tab] = false;
      };
      const familyMvpEnabled = cfg.enable_family_mvp !== false;
      if (familyMvpEnabled && cfg.enable_compliance_workflows !== true) {
        disableTab("trade-compliance");
        disableTab("trail");
        disableTab("taxtools");
      }
      if (familyMvpEnabled && cfg.enable_reporting_extended !== true) {
        disableTab("reports");
      }
      if (familyMvpEnabled && cfg.enable_advanced_analytics !== true) {
        disableTab("scenario");
      }
      for (const [tab, enabled] of Object.entries(tabs)) {
        if (enabled === false) disabledTabs.add(String(tab));
      }
      const theme = isTheme(cfg.theme) ? cfg.theme : "system";
      const stored =
        typeof window !== "undefined"
          ? window.localStorage.getItem("relativeViewEnabled")
          : null;
      setConfig((previousConfig) => ({
        relativeViewEnabled: stored
          ? stored === "true"
          : Boolean(cfg.relative_view_enabled),
        familyMvpEnabled,
        disabledTabs: Array.from(disabledTabs),
        tabs,
        theme,
        baseCurrency: previousConfig.baseCurrency,
        enableAdvancedAnalytics: cfg.enable_advanced_analytics !== false,
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
    <configContext.Provider value={{ ...config, refreshConfig, setRelativeViewEnabled, setBaseCurrency }}>
      {children}
    </configContext.Provider>
  );
}

export function useConfig() {
  return useContext(configContext);
}

export const SUPPORTED_CURRENCIES = [
  "CAD",
  "CHF",
  "EUR",
  "GBP",
  "GBX",
  "JPY",
  "USD",
];

export function BaseCurrencySelector() {
  const { baseCurrency, setBaseCurrency } = useConfig();
  const currencies = SUPPORTED_CURRENCIES;
  return (
    <select
      value={baseCurrency}
      onChange={(e) => setBaseCurrency(e.target.value)}
      aria-label="base currency"
    >
      {currencies.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
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
