import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import {
  RESOLVED_VIRTUAL_MODULE_ID,
  SHARED_DEPENDENCIES,
  VIRTUAL_MODULE_ID,
  allotmintPlugins,
  assertHostApiVersion,
  parsePluginEntries,
} from '../../../vite/allotmintPlugins';

type Hook = (this: unknown, ...args: unknown[]) => unknown;

const hostRoot = path.resolve(import.meta.dirname, '../../..');
let tmp: string;
let entryA: string;
let entryB: string;

function writeEntry(name: string, version: string): string {
  const file = path.join(tmp, name, 'index.ts');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(
    file,
    `export default { id: '${name}', hostApiVersion: ${version} };\n`
  );
  return file;
}

function hooks(entries: string | undefined) {
  const plugin = allotmintPlugins({ hostRoot, entries, cwd: tmp });
  return {
    config: () => (plugin.config as Hook).call({}),
    resolveId: (source: string, importer?: string, ctx: object = {}) =>
      (plugin.resolveId as Hook).call(ctx, source, importer, {}),
    load: (id: string) => (plugin.load as Hook).call({}, id),
  };
}

beforeAll(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'allotmint-plugins-'));
  entryA = writeEntry('alpha', 'HOST_API_VERSION');
  entryB = writeEntry('beta', '1');
});

afterAll(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('allotmintPlugins Vite plugin', () => {
  it('resolves the virtual id to its private id', () => {
    expect(hooks(undefined).resolveId(VIRTUAL_MODULE_ID)).toBe(
      RESOLVED_VIRTUAL_MODULE_ID
    );
    expect(hooks(undefined).resolveId('react', '/x/y.ts')).toBeNull();
  });

  it.each([undefined, '', `  ${path.delimiter} `])(
    'emits an empty plugin list and leaves config alone when entries are %j',
    (raw) => {
      const plugin = hooks(raw);
      expect(plugin.load(RESOLVED_VIRTUAL_MODULE_ID)).toBe(
        'export const plugins = [];\n'
      );
      expect(plugin.config()).toBeUndefined();
    }
  );

  it('ignores modules other than the virtual one', () => {
    expect(hooks(entryA).load('/src/main.tsx')).toBeNull();
  });

  it('imports every listed entry, in order', () => {
    const code = hooks([entryA, entryB].join(path.delimiter)).load(
      RESOLVED_VIRTUAL_MODULE_ID
    );
    expect(code).toBe(
      `import plugin0 from ${JSON.stringify(entryA.replaceAll('\\', '/'))};\n` +
        `import plugin1 from ${JSON.stringify(entryB.replaceAll('\\', '/'))};\n` +
        'export const plugins = [plugin0, plugin1].flat();\n'
    );
  });

  it('resolves relative entries against the working directory', () => {
    expect(parsePluginEntries(`alpha/index.ts${path.delimiter}`, tmp)).toEqual([
      entryA,
    ]);
  });

  it('fails the build when a listed entry does not exist', () => {
    const missing = path.join(tmp, 'missing', 'index.ts');
    expect(() => hooks(missing).load(RESOLVED_VIRTUAL_MODULE_ID)).toThrow(
      `ALLOTMINT_PLUGIN_ENTRIES lists ${missing}, which does not exist or is not a file.`
    );
  });

  it('fails the build when an entry targets another host API version', () => {
    const stale = writeEntry('stale', '2');
    expect(() => hooks(stale).load(RESOLVED_VIRTUAL_MODULE_ID)).toThrow(
      'declares hostApiVersion 2, but this allotmint build provides host API version 1'
    );
  });

  it('fails the build when an entry declares no hostApiVersion', () => {
    expect(() =>
      assertHostApiVersion('/p/index.ts', 'export default {};')
    ).toThrow(
      'ALLOTMINT_PLUGIN_ENTRIES: /p/index.ts does not declare hostApiVersion.'
    );
  });

  it('dedupes shared dependencies and allows entry directories when plugins are set', () => {
    const config = hooks(entryA).config() as {
      resolve: { dedupe: string[] };
      server: { fs: { allow: string[] } };
    };
    expect(config.resolve.dedupe).toEqual(SHARED_DEPENDENCIES);
    expect(config.server.fs.allow).toContain(path.dirname(entryA));
  });

  it('resolves bare imports from entry directories against the host', async () => {
    const resolve = vi
      .fn()
      .mockResolvedValue({ id: '/host/node_modules/react/index.js' });
    const plugin = hooks(entryA);

    await expect(
      plugin.resolveId('react', entryA, { resolve })
    ).resolves.toEqual({
      id: '/host/node_modules/react/index.js',
    });
    expect(resolve).toHaveBeenCalledWith(
      'react',
      path.join(hostRoot, 'src', 'main.tsx'),
      {
        skipSelf: true,
      }
    );
  });

  it('leaves relative imports and host-owned importers to Vite', () => {
    const resolve = vi.fn();
    const plugin = hooks(entryA);

    expect(plugin.resolveId('./page', entryA, { resolve })).toBeNull();
    expect(
      plugin.resolveId('react', path.join(hostRoot, 'src/App.tsx'), { resolve })
    ).toBeNull();
    expect(resolve).not.toHaveBeenCalled();
  });
});
