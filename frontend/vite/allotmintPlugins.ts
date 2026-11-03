/**
 * Build-time frontend plugins (#6836, ADR
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §4.2).
 *
 * Resolves `virtual:allotmint-plugins` to a module that imports each entry
 * file listed in ALLOTMINT_PLUGIN_ENTRIES (separated by path.delimiter: `:`
 * on POSIX, `;` on Windows) and exports them as `plugins`. Each entry's
 * default export is one AllotmintFrontendPlugin or an array of them.
 *
 * - Unset or empty: `export const plugins = [];`. Nothing is auto-detected
 *   from disk layout (e.g. a sibling allotmint-pro checkout), so the public
 *   build never depends on what happens to sit next to it.
 * - A listed entry that does not exist fails the build.
 * - An entry that declares a different hostApiVersion fails the build.
 * - Bare imports from entry directories resolve against the host's
 *   node_modules, with React, the router and i18n deduped, so a plugin
 *   directory needs no node_modules of its own.
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  normalizePath,
  searchForWorkspaceRoot,
  type Plugin,
  type UserConfig,
} from 'vite';
import { HOST_API_VERSION } from '../src/plugin-host/version.ts';

export const VIRTUAL_MODULE_ID = 'virtual:allotmint-plugins';
export const RESOLVED_VIRTUAL_MODULE_ID = `\0${VIRTUAL_MODULE_ID}`;
export const PLUGIN_ENTRIES_ENV = 'ALLOTMINT_PLUGIN_ENTRIES';
export const SHARED_DEPENDENCIES = [
  'react',
  'react-dom',
  'react-router-dom',
  'i18next',
  'react-i18next',
];

const EMPTY_MODULE = 'export const plugins = [];\n';
const HOST_API_VERSION_DECLARATION =
  /\bhostApiVersion\s*:\s*([A-Za-z_$][\w$]*|\d+)/g;

export interface AllotmintPluginsOptions {
  /** The host frontend directory (the one holding src/ and node_modules/). */
  hostRoot: string;
  /** Raw ALLOTMINT_PLUGIN_ENTRIES value; defaults to the environment's. */
  entries?: string;
  /** Directory relative entries resolve against; defaults to process.cwd(). */
  cwd?: string;
}

/** Absolute entry paths from an ALLOTMINT_PLUGIN_ENTRIES value. */
export function parsePluginEntries(
  raw: string | undefined,
  cwd: string,
  delimiter = path.delimiter
): string[] {
  if (!raw) return [];
  return raw
    .split(delimiter)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => path.resolve(cwd, entry));
}

/**
 * Throw unless `source` (an entry file's text) declares a hostApiVersion
 * this host accepts: the literal current version, or HOST_API_VERSION
 * imported from `@allotmint/host`, which matches by construction.
 */
export function assertHostApiVersion(
  entry: string,
  source: string,
  hostVersion = HOST_API_VERSION
): void {
  const declared = [...source.matchAll(HOST_API_VERSION_DECLARATION)].map(
    (match) => match[1]
  );
  if (declared.length === 0) {
    throw new Error(
      `${PLUGIN_ENTRIES_ENV}: ${entry} does not declare hostApiVersion.`
    );
  }
  for (const value of declared) {
    if (value === 'HOST_API_VERSION' || value === String(hostVersion)) continue;
    throw new Error(
      `${PLUGIN_ENTRIES_ENV}: ${entry} declares hostApiVersion ${value}, but this ` +
        `allotmint build provides host API version ${hostVersion}. Use the literal ` +
        `${hostVersion} or HOST_API_VERSION from @allotmint/host.`
    );
  }
}

function readEntry(entry: string): string {
  // Read directly rather than check-then-read: a separate existence check can
  // go stale before the read (CodeQL js/file-system-race).
  try {
    return fs.readFileSync(entry, 'utf-8');
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT' || code === 'EISDIR' || code === 'ENOTDIR') {
      throw new Error(
        `${PLUGIN_ENTRIES_ENV} lists ${entry}, which does not exist or is not a file.`,
        { cause: error }
      );
    }
    throw error;
  }
}

/** Source of `virtual:allotmint-plugins` for these entries. */
export function generatePluginsModule(entries: readonly string[]): string {
  if (entries.length === 0) return EMPTY_MODULE;
  for (const entry of entries) assertHostApiVersion(entry, readEntry(entry));
  const imports = entries.map(
    (entry, index) =>
      `import plugin${index} from ${JSON.stringify(normalizePath(entry))};`
  );
  const names = entries.map((_, index) => `plugin${index}`).join(', ');
  return `${imports.join('\n')}\nexport const plugins = [${names}].flat();\n`;
}

function isBareImport(source: string): boolean {
  return /^[\w@][^:]*$/.test(source) && !path.isAbsolute(source);
}

function isInside(file: string, directories: readonly string[]): boolean {
  const resolved = path.resolve(file.split('?')[0]);
  return directories.some((dir) => {
    const relative = path.relative(dir, resolved);
    return (
      relative !== '' &&
      !relative.startsWith('..') &&
      !path.isAbsolute(relative)
    );
  });
}

export function allotmintPlugins(options: AllotmintPluginsOptions): Plugin {
  const raw = options.entries ?? process.env[PLUGIN_ENTRIES_ENV];
  const entries = parsePluginEntries(raw, options.cwd ?? process.cwd());
  const entryDirs = [...new Set(entries.map((entry) => path.dirname(entry)))];
  const hostImporter = path.join(options.hostRoot, 'src', 'main.tsx');

  return {
    name: 'allotmint-plugins',
    enforce: 'pre',
    config(): UserConfig | undefined {
      if (entries.length === 0) return undefined;
      return {
        resolve: { dedupe: SHARED_DEPENDENCIES },
        server: {
          fs: {
            allow: [searchForWorkspaceRoot(options.hostRoot), ...entryDirs],
          },
        },
      };
    },
    resolveId(source, importer) {
      if (source === VIRTUAL_MODULE_ID) return RESOLVED_VIRTUAL_MODULE_ID;
      if (!importer || entries.length === 0 || !isBareImport(source))
        return null;
      if (!isInside(importer, entryDirs)) return null;
      return this.resolve(source, hostImporter, { skipSelf: true });
    },
    load(id) {
      if (id !== RESOLVED_VIRTUAL_MODULE_ID) return null;
      return generatePluginsModule(entries);
    },
  };
}
