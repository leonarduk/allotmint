import { lazy, type LazyExoticComponent, type ComponentType } from 'react';
import type { Mode } from './modes';
import { isDefaultGroupSlug } from './utils/groups';

export type PageSection = 'user' | 'support' | 'standalone';
export type MenuCategoryId =
  | 'dashboard'
  | 'insights'
  | 'goals'
  | 'operations'
  | 'preferences';

export interface PageRouteContext {
  selectedOwner?: string;
  selectedGroup?: string;
}

export interface PageDefinition {
  mode: Mode;
  routeSegment: string | null;
  section: PageSection;
  menuCategory?: MenuCategoryId;
  priority?: number;
  defaultPath: (context: PageRouteContext) => string;
  lazyComponent?: LazyExoticComponent<ComponentType>;
  routePath?: string;
}

const lazyPage = (loader: Parameters<typeof lazy>[0]) => lazy(loader);

export const pageManifest = [
  {
    mode: 'group',
    routeSegment: null,
    section: 'user',
    menuCategory: 'dashboard',
    priority: 0,
    defaultPath: ({ selectedGroup }) =>
      selectedGroup && !isDefaultGroupSlug(selectedGroup)
        ? `/?group=${selectedGroup}`
        : '/',
  },
  {
    mode: 'market',
    routeSegment: 'market',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 5,
    defaultPath: () => '/market',
  },
  {
    mode: 'movers',
    routeSegment: 'movers',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 10,
    defaultPath: () => '/movers',
  },
  {
    mode: 'instrument',
    routeSegment: 'instrument',
    section: 'user',
    menuCategory: 'insights',
    priority: 20,
    defaultPath: ({ selectedGroup }) =>
      selectedGroup ? `/instrument/${selectedGroup}` : '/instrument',
  },
  {
    mode: 'owner',
    routeSegment: 'portfolio',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 30,
    defaultPath: ({ selectedOwner }) =>
      selectedOwner ? `/portfolio/${selectedOwner}` : '/portfolio',
  },
  {
    mode: 'performance',
    routeSegment: 'performance',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 40,
    defaultPath: ({ selectedOwner }) =>
      selectedOwner ? `/performance/${selectedOwner}` : '/performance',
  },
  {
    mode: 'transactions',
    routeSegment: 'transactions',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 50,
    defaultPath: () => '/transactions',
  },
  {
    mode: 'trading',
    routeSegment: 'trading',
    section: 'user',
    menuCategory: 'insights',
    priority: 55,
    defaultPath: () => '/trading',
  },
  {
    mode: 'screener',
    routeSegment: 'screener',
    section: 'user',
    menuCategory: 'insights',
    priority: 60,
    defaultPath: () => '/screener',
  },
  {
    mode: 'timeseries',
    routeSegment: 'timeseries',
    section: 'support',
    menuCategory: 'operations',
    priority: 70,
    defaultPath: () => '/timeseries',
  },
  {
    mode: 'watchlist',
    routeSegment: 'watchlist',
    section: 'user',
    menuCategory: 'insights',
    priority: 80,
    defaultPath: () => '/watchlist',
  },
  {
    mode: 'allocation',
    routeSegment: 'allocation',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 85,
    defaultPath: () => '/allocation',
  },
  {
    mode: 'instrumentadmin',
    routeSegment: 'instrumentadmin',
    section: 'support',
    menuCategory: 'operations',
    priority: 85,
    defaultPath: () => '/instrumentadmin',
  },
  {
    mode: 'rebalance',
    routeSegment: 'rebalance',
    section: 'user',
    menuCategory: 'insights',
    priority: 86,
    defaultPath: () => '/rebalance',
  },
  {
    mode: 'dataadmin',
    routeSegment: 'dataadmin',
    section: 'support',
    menuCategory: 'operations',
    priority: 90,
    defaultPath: () => '/dataadmin',
  },
  {
    mode: 'reports',
    routeSegment: 'reports',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 100,
    defaultPath: () => '/reports',
  },
  {
    mode: 'trail',
    routeSegment: 'trail',
    section: 'user',
    menuCategory: 'goals',
    priority: 102,
    defaultPath: () => '/trail',
    routePath: '/trail',
    lazyComponent: lazyPage(() => import('./pages/Trail')),
  },
  {
    mode: 'alertsettings',
    routeSegment: 'alert-settings',
    section: 'user',
    menuCategory: 'preferences',
    priority: 104,
    defaultPath: () => '/alert-settings',
    routePath: '/alert-settings',
    lazyComponent: lazyPage(() => import('./pages/AlertSettings')),
  },
  {
    mode: 'settings',
    routeSegment: 'settings',
    section: 'user',
    menuCategory: 'preferences',
    priority: 105,
    defaultPath: () => '/settings',
  },
  {
    mode: 'pension',
    routeSegment: 'pension',
    section: 'user',
    menuCategory: 'goals',
    priority: 107,
    defaultPath: () => '/pension/forecast',
  },
  {
    mode: 'taxtools',
    routeSegment: 'tax-tools',
    section: 'user',
    menuCategory: 'goals',
    priority: 108,
    defaultPath: () => '/tax-tools',
  },
  {
    mode: 'trade-compliance',
    routeSegment: 'trade-compliance',
    section: 'user',
    menuCategory: 'goals',
    priority: 110,
    defaultPath: () => '/trade-compliance',
    routePath: '/trade-compliance',
    lazyComponent: lazyPage(() => import('./pages/TradeCompliance')),
  },
  {
    mode: 'support',
    routeSegment: 'support',
    section: 'support',
    menuCategory: 'preferences',
    priority: 110,
    defaultPath: () => '/support',
    routePath: '/support',
    lazyComponent: lazyPage(() => import('./pages/Support')),
  },
  {
    mode: 'scenario',
    routeSegment: 'scenario',
    section: 'user',
    menuCategory: 'insights',
    priority: 120,
    defaultPath: () => '/scenario',
  },
  {
    mode: 'virtual',
    routeSegment: 'virtual',
    section: 'standalone',
    defaultPath: () => '/virtual',
    routePath: '/virtual',
    lazyComponent: lazyPage(() => import('./pages/VirtualPortfolio')),
  },
  {
    mode: 'research',
    routeSegment: 'research',
    section: 'user',
    defaultPath: () => '/research',
  },
] satisfies PageDefinition[];

export const pageManifestByMode = Object.fromEntries(
  pageManifest.map((page) => [page.mode, page])
) as Record<Mode, PageDefinition>;

export const pageManifestBySegment = new Map(
  pageManifest
    .filter((page) => page.routeSegment !== null)
    .map((page) => [page.routeSegment, page] as const)
);

export const menuCategories = {
  user: [
    { id: 'dashboard', titleKey: 'dashboard' },
    { id: 'insights', titleKey: 'insights' },
    { id: 'goals', titleKey: 'goals' },
    { id: 'preferences', titleKey: 'preferences' },
  ],
  support: [
    { id: 'operations', titleKey: 'operations' },
    { id: 'preferences', titleKey: 'preferences' },
  ],
} as const;

export function deriveModeFromPathname(pathname: string): Mode {
  const segments = pathname.split('/').filter(Boolean);
  const [first] = segments;
  if (first === undefined) return 'group';
  return pageManifestBySegment.get(first)?.mode ?? 'movers';
}

export function pathForMode(
  mode: Mode,
  context: PageRouteContext = {}
): string {
  return pageManifestByMode[mode].defaultPath(context);
}

export const standalonePageRoutes = pageManifest.filter(
  (page) => page.routePath && page.lazyComponent
);
