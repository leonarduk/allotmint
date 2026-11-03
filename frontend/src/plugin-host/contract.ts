/**
 * The frontend plugin contract (#6836, ADR
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §4.3).
 *
 * A plugin is a build-time addition: `vite/allotmintPlugins.ts` imports the
 * entry files listed in ALLOTMINT_PLUGIN_ENTRIES into
 * `virtual:allotmint-plugins`. The public build lists none, so it contains
 * no plugin code at all.
 *
 * Only pages and tab defaults exist so far. Slots, `familyMvpFlag` and
 * plugin locales arrive with step 2 of the ADR's migration plan.
 */
import type { RouteRegistryEntry } from '../routes/registry';
import { HOST_API_VERSION } from './version';

export { HOST_API_VERSION };

/**
 * Named places in free pages where a plugin may mount a fragment. Declared
 * now so the names are fixed; nothing renders them until step 2.
 */
export type SlotName =
  'dashboard.banner' | 'ideas.tab' | 'owner.actions' | 'rightRail.section';

/**
 * A page a plugin adds: the same shape as a routes/registry.ts entry. Its
 * `mode` is a plain string because plugin modes are, by design, not part of
 * the free `Mode` union.
 */
export type PluginPageEntry = Omit<RouteRegistryEntry, 'mode'> & {
  mode: string;
};

export interface AllotmintFrontendPlugin {
  /** Namespace for config, i18n keys and slot keys, e.g. "compliance". */
  id: string;
  /** Must equal HOST_API_VERSION; checked at build time and on load. */
  hostApiVersion: typeof HOST_API_VERSION;
  /** Whole pages, appended to the page manifest after the free entries. */
  pages?: readonly PluginPageEntry[];
  /**
   * Defaults merged into the runtime `tabs` config. Keys must be modes of
   * this plugin's own pages; `/config` overrides still apply on top.
   */
  configDefaults?: { tabs?: Readonly<Record<string, boolean>> };
}
