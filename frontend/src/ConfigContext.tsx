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

const LEGACY_BASE_CURRENCY_KEY = "baseCurrency";

/** ``base_currency`` from /config as a 3-letter code; anything else is GBP (#9768). */
export function parseReportingCurrency(raw: unknown): string {
  const code = typeof raw === "string" ? raw.trim().toUpperCase() : "";
  if (!/^[A-Z]{3}$/.test(code) || code === "GBX") return "GBP";
  return code;
}

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
  dataexplorer: boolean;
  dataquality: boolean;
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
  plot: boolean;
  awscosts: boolean;
}

export interface AppConfig {
  configLoaded: boolean;
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
  /**
   * The configured ``base_currency`` (#9768). Every ``*_gbp`` value is in
   * pounds and ``money()`` only labels, so never format with this directly:
   * ``useReportingCurrency`` converts GBP amounts into it, falling back to
   * GBP while no rate is available (#9753).
   */
  reportingCurrency: string;
  enableAdvancedAnalytics?: boolean;
  /**
   * Read-write Data Quality Admin surface (issue list + preview/fix/audit).
   * Fails open: the read-only series table stays available even when this is
   * false, only the write tabs (Issues/Holdings/Audit) are hidden.
   */
  dataQualityAdmin?: boolean;
}

export interface RawConfig {
  relative_view_enabled?: boolean | null;
  tabs?: Partial<TabsConfig>;
  disabled_tabs?: string[];
  enable_family_mvp?: boolean;
  enable_compliance_workflows?: boolean;
  enable_advanced_analytics?: boolean;
  enable_reporting_extended?: boolean;
  enable_data_quality_admin?: boolean;
  theme?: string | null;
  allowed_emails?: string[] | null;
  base_currency?: string | null;
}

const defaultTabs: TabsConfig = {
  group: true,
  market: true,
  owner: true,
  instrument: true,
  performance: true,
  // transactions enabled by default; Family MVP uses /transactions as its
  // entry point so it must remain on. Non-MVP deployments also show it.
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
  dataexplorer: true,
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
  dataquality: true,
  plot: true,
  awscosts: true,
  // Not a named TabsConfig property (falls back to the string index
  // signature) so existing config fixtures that omit it don't need updating;
  // it just needs to default to enabled like every other user-facing tab.
  help: true,
};

export interface ConfigContextValue extends AppConfig {
  refreshConfig: () => Promise<void>;
  setRelativeViewEnabled: (enabled: boolean) => void;
}

export const configContext = createContext<ConfigContextValue>({
  configLoaded: false,
  relativeViewEnabled: false,
  // Default to false (show everything) until server config confirms MVP mode.
  // Failing open is safer than briefly hiding UI from non-MVP users.
  familyMvpEnabled: false,
  disabledTabs: [],
  tabs: defaultTabs,
  theme: "system",
  reportingCurrency: "GBP",
  enableAdvancedAnalytics: true,
  dataQualityAdmin: true,
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>(() => {
    const storedRel =
      typeof window !== "undefined"
        ? window.localStorage.getItem("relativeViewEnabled")
        : null;
    return {
      configLoaded: false,
      relativeViewEnabled: storedRel === "true",
      // Default to false until the /config fetch resolves, so non-MVP users
      // never see a flash of MVP-restricted UI on page load.
      familyMvpEnabled: false,
      disabledTabs: [],
      tabs: defaultTabs,
      theme: "system",
      reportingCurrency: "GBP",
      enableAdvancedAnalytics: true,
      dataQualityAdmin: true,
    };
  });
  const setRelativeViewEnabled = useCallback((enabled: boolean) => {
    setConfig((prev) => ({ ...prev, relativeViewEnabled: enabled }));
    if (typeof window !== "undefined") {
      window.localStorage.setItem("relativeViewEnabled", String(enabled));
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
        disabledTabs.add(String(tab));
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
      setConfig(() => ({
        configLoaded: true,
        relativeViewEnabled: stored
          ? stored === "true"
          : Boolean(cfg.relative_view_enabled),
        familyMvpEnabled,
        disabledTabs: Array.from(disabledTabs),
        tabs,
        theme,
        reportingCurrency: parseReportingCurrency(cfg.base_currency),
        enableAdvancedAnalytics: cfg.enable_advanced_analytics !== false,
        dataQualityAdmin: cfg.enable_data_quality_admin !== false,
      }));
      applyTheme(theme);
    } catch {
      setConfig((previousConfig) => ({
        ...previousConfig,
        configLoaded: true,
      }));
    }
  }, []);

  useEffect(() => {
    // A base currency once chosen with the old (since removed) selector used
    // to relabel GBP values as that currency; it is never read (#9753).
    window.localStorage.removeItem(LEGACY_BASE_CURRENCY_KEY);
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

export const SUPPORTED_CURRENCIES = [
  "CAD",
  "CHF",
  "EUR",
  "GBP",
  "GBX",
  "JPY",
  "USD",
];

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
