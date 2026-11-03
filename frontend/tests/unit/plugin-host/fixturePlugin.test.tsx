import { Suspense } from 'react';
import { render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import examplePlugin from '@/plugin-host/__fixtures__/examplePlugin';
import type { AllotmintFrontendPlugin } from '@/plugin-host/contract';

/*
 * The "plugin present" path, exercised in OSS CI with a fixture plugin
 * instead of the real allotmint-pro code (#6836, ADR §4.5). Each test swaps
 * the generated plugin list and re-imports the modules that consume it.
 */

function usePlugins(plugins: readonly AllotmintFrontendPlugin[]) {
  vi.resetModules();
  vi.doMock('virtual:allotmint-plugins', () => ({ plugins }));
}

afterEach(() => {
  vi.doUnmock('virtual:allotmint-plugins');
  vi.resetModules();
});

describe('page manifest with a fixture plugin', () => {
  it('appends exactly one route after the free entries', async () => {
    usePlugins([]);
    const free = (await import('@/routes/registry')).ROUTE_REGISTRY.map(
      (e) => e.mode
    );

    usePlugins([examplePlugin]);
    const registry = await import('@/routes/registry');

    expect(registry.ROUTE_REGISTRY.map((e) => e.mode)).toEqual([
      ...free,
      'example-plugin',
    ]);
    expect(registry.standalonePageRoutes.at(-1)?.routePath).toBe(
      '/example-plugin'
    );
    expect(registry.deriveModeFromPathname('/example-plugin')).toBe(
      'example-plugin'
    );
    expect(registry.getMenuEntries('user').at(-1)?.mode).toBe('example-plugin');
  });

  it('renders the plugin page through its lazy component', async () => {
    usePlugins([examplePlugin]);
    const { standalonePageRoutes } = await import('@/routes/registry');
    const PluginPage = standalonePageRoutes.at(-1)!.lazyComponent;

    render(
      <Suspense fallback={null}>
        <PluginPage />
      </Suspense>
    );

    expect(await screen.findByText('Example plugin page')).toBeInTheDocument();
  });

  it('fails on load when a plugin page reuses a free mode', async () => {
    const clash: AllotmintFrontendPlugin = {
      ...examplePlugin,
      pages: [
        { ...examplePlugin.pages![0], mode: 'screener', routeSegment: 'x' },
      ],
      configDefaults: {},
    };
    usePlugins([clash]);

    await expect(import('@/routes/registry')).rejects.toThrow(
      'Frontend plugin "example" uses "screener", which the free app already uses.'
    );
  });

  it('fails on load when a plugin targets another host API version', async () => {
    usePlugins([
      {
        ...examplePlugin,
        hostApiVersion: 7,
      } as unknown as AllotmintFrontendPlugin,
    ]);

    await expect(import('@/plugin-host/registry')).rejects.toThrow(
      'targets host API version 7, but this allotmint build provides version 1'
    );
  });
});

describe('ConfigContext with a fixture plugin', () => {
  it('adds exactly one default tab and keeps every free default', async () => {
    usePlugins([]);
    const freeConfig = await import('@/ConfigContext');
    const freeTabs = renderHook(() => freeConfig.useConfig()).result.current
      .tabs;

    usePlugins([examplePlugin]);
    const config = await import('@/ConfigContext');
    const tabs = renderHook(() => config.useConfig()).result.current.tabs;

    expect(tabs).toEqual({ ...freeTabs, 'example-plugin': true });
  });
});
