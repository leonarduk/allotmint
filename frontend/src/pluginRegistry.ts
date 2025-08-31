import AlertSettings from "./pages/AlertSettings";
import ComplianceWarnings from "./pages/ComplianceWarnings";

export interface TabPlugin {
  /** Unique identifier for the plugin */
  id: string;
  /** React component that renders the tab */
  Component: React.ComponentType;
  /** Optional priority used for ordering (higher comes first) */
  priority?: number;
  /**
   * Optional flag or function determining whether the plugin is enabled.
   * When omitted the plugin is considered enabled.
   */
  isEnabled?: boolean | (() => boolean);
}

const registry: TabPlugin[] = [];

/** Register a new tab plugin. */
export function registerTabPlugin(plugin: TabPlugin) {
  registry.push(plugin);
}

/**
 * Retrieve all enabled tab plugins ordered by priority.
 * Plugins with a higher priority value appear earlier.
 */
export function getTabPlugins(): TabPlugin[] {
  return registry
    .filter((p) => {
      const enabled =
        typeof p.isEnabled === "function" ? p.isEnabled() : p.isEnabled;
      return enabled !== false;
    })
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
}

/** Clear all registered plugins. Primarily for testing. */
export function clearTabPlugins() {
  registry.length = 0;
}


// Register built-in pages
registerTabPlugin({
  id: "alert-settings",
  Component: AlertSettings,
  priority: 130,
});

registerTabPlugin({
  id: "compliance",
  Component: ComplianceWarnings,
  priority: 150,
});
