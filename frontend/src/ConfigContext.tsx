import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getConfig } from "./api";

export interface AppConfig {
  relativeViewEnabled: boolean;
}

export const ConfigContext = createContext<AppConfig>({ relativeViewEnabled: false });

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>({ relativeViewEnabled: false });

  useEffect(() => {
    getConfig()
      .then((cfg) =>
        setConfig({
          relativeViewEnabled: Boolean((cfg as any).relative_view_enabled),
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

