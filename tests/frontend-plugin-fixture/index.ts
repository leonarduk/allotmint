/**
 * Frontend plugin fixture that lives OUTSIDE frontend/ on purpose (#6836,
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §4.5). CI builds the
 * frontend with ALLOTMINT_PLUGIN_ENTRIES pointing here
 * (frontend/scripts/verify-plugin-build.mjs) to prove that an entry in
 * another directory resolves `@allotmint/host` and bare imports such as
 * `react` against the host's node_modules, and that the public build never
 * contains this fixture's marker string.
 *
 * This directory deliberately has no package.json or node_modules.
 */
import { lazy } from 'react';
import {
  HOST_API_VERSION,
  type AllotmintFrontendPlugin,
} from '@allotmint/host';

const fixturePlugin: AllotmintFrontendPlugin = {
  id: 'build-fixture',
  hostApiVersion: HOST_API_VERSION,
  pages: [
    {
      mode: 'plugin-build-fixture',
      routeSegment: 'plugin-build-fixture',
      section: 'standalone',
      priority: 900,
      defaultPath: () => '/plugin-build-fixture',
      routePath: '/plugin-build-fixture',
      lazyComponent: lazy(() => import('./FixturePage')),
    },
  ],
  configDefaults: { tabs: { 'plugin-build-fixture': true } },
};

export default fixturePlugin;
