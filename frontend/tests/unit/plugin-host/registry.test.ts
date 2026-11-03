import { describe, expect, it } from 'vitest';
import examplePlugin from '@/plugin-host/__fixtures__/examplePlugin';
import type { AllotmintFrontendPlugin } from '@/plugin-host/contract';
import {
  assertNoCollisions,
  collectPluginPages,
  collectPluginTabDefaults,
  loadedPlugins,
  pluginPages,
  pluginTabDefaults,
  validatePlugins,
} from '@/plugin-host/registry';

function withPage(
  id: string,
  mode: string,
  routeSegment = mode
): AllotmintFrontendPlugin {
  return {
    ...examplePlugin,
    id,
    pages: [{ ...examplePlugin.pages![0], mode, routeSegment }],
    configDefaults: { tabs: { [mode]: true } },
  };
}

describe('plugin-host registry', () => {
  it('loads no plugins in the free build', () => {
    expect(loadedPlugins).toEqual([]);
    expect(pluginPages).toEqual([]);
    expect(pluginTabDefaults).toEqual({});
  });

  it('collects pages and tab defaults from a plugin', () => {
    expect(
      collectPluginPages([examplePlugin]).map((page) => page.mode)
    ).toEqual(['example-plugin']);
    expect(collectPluginTabDefaults([examplePlugin])).toEqual({
      'example-plugin': true,
    });
  });

  it('rejects a plugin built against another host API version', () => {
    const stale = {
      ...examplePlugin,
      hostApiVersion: 2,
    } as unknown as AllotmintFrontendPlugin;
    expect(() => validatePlugins([stale])).toThrow(
      'Frontend plugin "example" targets host API version 2, but this allotmint build provides version 1.'
    );
  });

  it('rejects two plugins with the same id', () => {
    expect(() => validatePlugins([examplePlugin, examplePlugin])).toThrow(
      'Frontend plugin id "example" is registered twice.'
    );
  });

  it('rejects a tab default for a mode the plugin does not own', () => {
    const meddler: AllotmintFrontendPlugin = {
      ...examplePlugin,
      configDefaults: { tabs: { screener: false } },
    };
    expect(() => collectPluginTabDefaults([meddler])).toThrow(
      'Frontend plugin "example" sets a default for tab "screener", which is not one of its own page modes.'
    );
  });

  it('rejects a plugin page that reuses a free mode or segment', () => {
    expect(() =>
      assertNoCollisions(['screener'], [withPage('p', 'screener')])
    ).toThrow(
      'Frontend plugin "p" uses "screener", which the free app already uses.'
    );
    expect(() =>
      assertNoCollisions(['tax-tools'], [withPage('p', 'tax', 'tax-tools')])
    ).toThrow(
      'Frontend plugin "p" uses "tax-tools", which the free app already uses.'
    );
  });

  it('rejects two plugins claiming the same mode', () => {
    expect(() =>
      assertNoCollisions(
        [],
        [withPage('first', 'shared'), withPage('second', 'shared')]
      )
    ).toThrow(
      'Frontend plugin "second" uses "shared", which plugin "first" already uses.'
    );
  });

  it('accepts plugins with distinct keys', () => {
    expect(() =>
      assertNoCollisions(
        ['group'],
        [withPage('a', 'alpha'), withPage('b', 'beta')]
      )
    ).not.toThrow();
  });
});
