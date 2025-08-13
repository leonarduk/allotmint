import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getConfig } from "./api";

export interface AppConfig {
  relativeViewEnabled: boolean;
  /**
   * Tabs that should be hidden/disabled from the UI.  We keep the type
   * flexible here so that the context can be consumed without depending on
   * the `Mode` union defined in `App.tsx`.
   */
  disabledTabs?: string[];
}

export const ConfigContext = createContext<AppConfig>({
  relativeViewEnabled: false,
  disabledTabs: [],
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({
    relativeViewEnabled: false,
    disabledTabs: [],
  });

  useEffect(() => {
    getConfig()
      .then((cfg) =>
        setConfig({
          relativeViewEnabled: Boolean((cfg as any).relative_view_enabled),
          disabledTabs: Array.isArray((cfg as any).disabled_tabs)
            ? ((cfg as any).disabled_tabs as string[])
            : [],
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

