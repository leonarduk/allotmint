/**
 * The one module that imports `virtual:allotmint-plugins` (#6836, ADR
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §4.2). An ESLint
 * no-restricted-imports rule keeps every other file away from it.
 *
 * With ALLOTMINT_PLUGIN_ENTRIES unset (the public build) the virtual module
 * is `export const plugins = [];`, so everything exported here is empty and
 * free behaviour is unchanged.
 */
import { plugins as configuredPlugins } from 'virtual:allotmint-plugins';
import {
  HOST_API_VERSION,
  type AllotmintFrontendPlugin,
  type PluginPageEntry,
} from './contract';

/** Throw unless every plugin targets this host's API version and has a unique id. */
export function validatePlugins(
  plugins: readonly AllotmintFrontendPlugin[]
): void {
  const seenIds = new Set<string>();
  for (const plugin of plugins) {
    if (plugin.hostApiVersion !== HOST_API_VERSION) {
      throw new Error(
        `Frontend plugin "${plugin.id}" targets host API version ` +
          `${String(plugin.hostApiVersion)}, but this allotmint build provides ` +
          `version ${HOST_API_VERSION}.`
      );
    }
    if (seenIds.has(plugin.id)) {
      throw new Error(`Frontend plugin id "${plugin.id}" is registered twice.`);
    }
    seenIds.add(plugin.id);
  }
}

/** Every plugin's pages, in plugin order. */
export function collectPluginPages(
  plugins: readonly AllotmintFrontendPlugin[]
): PluginPageEntry[] {
  return plugins.flatMap((plugin) => plugin.pages ?? []);
}

/**
 * Every plugin's tab defaults. A plugin may only set defaults for the modes
 * of its own pages, so it can never toggle a free tab or another plugin's.
 */
export function collectPluginTabDefaults(
  plugins: readonly AllotmintFrontendPlugin[]
): Record<string, boolean> {
  const defaults: Record<string, boolean> = {};
  for (const plugin of plugins) {
    const ownModes = new Set((plugin.pages ?? []).map((page) => page.mode));
    for (const [tab, enabled] of Object.entries(
      plugin.configDefaults?.tabs ?? {}
    )) {
      if (!ownModes.has(tab)) {
        throw new Error(
          `Frontend plugin "${plugin.id}" sets a default for tab "${tab}", ` +
            'which is not one of its own page modes.'
        );
      }
      defaults[tab] = enabled;
    }
  }
  return defaults;
}

function pluginKeys(plugin: AllotmintFrontendPlugin): Set<string> {
  const keys = new Set<string>();
  for (const page of plugin.pages ?? []) {
    keys.add(page.mode);
    if (page.routeSegment) keys.add(page.routeSegment);
  }
  for (const tab of Object.keys(plugin.configDefaults?.tabs ?? {}))
    keys.add(tab);
  return keys;
}

/**
 * Throw if a plugin's page modes, route segments or tab keys collide with
 * a free key or with another plugin's. Called on module load by the page
 * manifest (free modes and segments) and by ConfigContext (free tab keys),
 * so a collision fails the app, and its unit tests, immediately.
 */
export function assertNoCollisions(
  freeKeys: Iterable<string>,
  plugins: readonly AllotmintFrontendPlugin[] = loadedPlugins
): void {
  const owners = new Map<string, string>();
  for (const key of freeKeys) owners.set(key, 'the free app');
  for (const plugin of plugins) {
    for (const key of pluginKeys(plugin)) {
      const owner = owners.get(key);
      if (owner !== undefined) {
        throw new Error(
          `Frontend plugin "${plugin.id}" uses "${key}", which ${owner} already uses.`
        );
      }
      owners.set(key, `plugin "${plugin.id}"`);
    }
  }
}

validatePlugins(configuredPlugins);

/** The plugins this build was assembled with (none in the public build). */
export const loadedPlugins: readonly AllotmintFrontendPlugin[] =
  configuredPlugins;

/** Plugin pages, appended to the page manifest after the free entries. */
export const pluginPages: readonly PluginPageEntry[] =
  collectPluginPages(loadedPlugins);

/** Plugin tab defaults, merged into ConfigContext's default tabs. */
export const pluginTabDefaults: Readonly<Record<string, boolean>> =
  collectPluginTabDefaults(loadedPlugins);
