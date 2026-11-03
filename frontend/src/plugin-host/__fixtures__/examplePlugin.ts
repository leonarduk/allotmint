/**
 * Fixture plugin for the plugin-host unit tests (#6836). Nothing in the app
 * imports it; the tests hand it to the registry through a mocked
 * `virtual:allotmint-plugins`.
 */
import { lazy } from 'react';
import {
  HOST_API_VERSION,
  type AllotmintFrontendPlugin,
} from '@allotmint/host';

const examplePlugin: AllotmintFrontendPlugin = {
  id: 'example',
  hostApiVersion: HOST_API_VERSION,
  pages: [
    {
      mode: 'example-plugin',
      routeSegment: 'example-plugin',
      section: 'user',
      menuCategory: 'insights',
      priority: 500,
      defaultPath: () => '/example-plugin',
      routePath: '/example-plugin',
      lazyComponent: lazy(() => import('./ExamplePluginPage')),
    },
  ],
  configDefaults: { tabs: { 'example-plugin': true } },
};

export default examplePlugin;
