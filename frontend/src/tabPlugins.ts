import { PAGE_MANIFEST } from "./pageManifest";

export const tabPluginMap = Object.fromEntries(
  PAGE_MANIFEST.filter((entry) => entry.menu).map((entry) => [entry.mode, {}]),
) as Record<string, Record<string, never>>;
export type TabPluginId = keyof typeof tabPluginMap;

export const orderedTabPlugins = PAGE_MANIFEST.filter((entry) => entry.menu).map((entry) => ({
  id: entry.mode as TabPluginId,
  priority: entry.order,
  section: entry.menu!.section,
  category: entry.menu!.category,
}));

export const USER_TABS = orderedTabPlugins
  .filter((plugin) => plugin.section === "user")
  .map((plugin) => plugin.id);
export const SUPPORT_TABS = orderedTabPlugins
  .filter((plugin) => plugin.section === "support")
  .map((plugin) => plugin.id);
export type TabPlugin = (typeof orderedTabPlugins)[number];
