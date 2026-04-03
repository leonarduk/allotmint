import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { TabsConfig } from '../ConfigContext';
import type { Mode } from '../modes';
import { isDefaultGroupSlug } from '../utils/groups';

export type RouteSection = 'user' | 'support' | 'standalone';
export type MenuSection = Extract<RouteSection, 'user' | 'support'>;
export type MenuCategory =
  | 'dashboard'
  | 'insights'
  | 'goals'
  | 'preferences'
  | 'operations';

export interface RoutePathContext {
  owner?: string;
  group?: string;
  selectedOwner?: string;
  selectedGroup?: string;
}

export interface RouteRegistryEntry {
  mode: Mode;
  routeSegment: string | null;
  section: RouteSection;
  menuCategory?: MenuCategory;
  priority?: number;
  defaultPath: (context: RoutePathContext) => string;
  routePath?: string;
  lazyComponent?: LazyExoticComponent<ComponentType>;
}

export interface DerivedRoute {
  mode: Mode;
  routeSegment: string | null;
  slug: string;
}

const lazyPage = (loader: Parameters<typeof lazy>[0]) => lazy(loader);
const routeContext = ({
  owner,
  group,
  selectedOwner,
  selectedGroup,
}: RoutePathContext) => ({
  owner: owner ?? selectedOwner ?? '',
  group: group ?? selectedGroup ?? '',
});

export const ROUTE_REGISTRY: RouteRegistryEntry[] = [
  {
    mode: 'group',
    routeSegment: null,
    section: 'user',
    menuCategory: 'dashboard',
    priority: 0,
    defaultPath: ({ group, selectedGroup }) => {
      const resolvedGroup = group ?? selectedGroup ?? '';
      return resolvedGroup && !isDefaultGroupSlug(resolvedGroup)
        ? `/?group=${resolvedGroup}`
        : '/';
    },
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
    defaultPath: (context) => {
      const { group } = routeContext(context);
      return group ? `/instrument/${group}` : '/instrument';
    },
  },
  {
    mode: 'owner',
    routeSegment: 'portfolio',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 30,
    defaultPath: (context) => {
      const { owner } = routeContext(context);
      return owner ? `/portfolio/${owner}` : '/portfolio';
    },
  },
  {
    mode: 'performance',
    routeSegment: 'performance',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 40,
    defaultPath: (context) => {
      const { owner } = routeContext(context);
      return owner ? `/performance/${owner}` : '/performance';
    },
  },
  {
    mode: 'transactions',
    routeSegment: 'transactions',
    section: 'user',
    menuCategory: 'dashboard',
    priority: 25,
    defaultPath: () => '/input',
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
    lazyComponent: lazyPage(() => import('../pages/Trail')),
  },
  {
    // No lazyComponent here by design: <Alerts /> is rendered eagerly inside App.tsx via the
    // `mode === 'alerts'` branch, not via the standalonePageRoutes registry loop. This entry
    // exists solely so that deriveModeFromPathname('/alerts') returns 'alerts' and navigation
    // UI can be generated. standalonePageRoutes filters on `routePath && lazyComponent`, so
    // this entry is never added to the React Router <Route> list.
    mode: 'alerts',
    routeSegment: 'alerts',
    section: 'standalone',
    priority: 103,
    defaultPath: () => '/alerts',
  },
  {
    mode: 'alertsettings',
    routeSegment: 'alert-settings',
    section: 'user',
    menuCategory: 'preferences',
    priority: 104,
    defaultPath: () => '/alert-settings',
    routePath: '/alert-settings',
    lazyComponent: lazyPage(() => import('../pages/AlertSettings')),
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
    lazyComponent: lazyPage(() => import('../pages/TradeCompliance')),
  },
  {
    mode: 'support',
    routeSegment: 'support',
    section: 'support',
    menuCategory: 'preferences',
    priority: 110,
    defaultPath: () => '/support',
    routePath: '/support',
    lazyComponent: lazyPage(() => import('../pages/Support')),
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
    priority: 130,
    defaultPath: () => '/virtual',
    routePath: '/virtual',
    lazyComponent: lazyPage(() => import('../pages/VirtualPortfolio')),
  },
  {
    mode: 'research',
    routeSegment: 'research',
    section: 'user',
    menuCategory: 'insights',
    priority: 140,
    defaultPath: () => '/research',
  },
];

export const pageManifest = ROUTE_REGISTRY;
export const PAGE_MANIFEST = ROUTE_REGISTRY;

export const pageManifestByMode = Object.fromEntries(
  ROUTE_REGISTRY.map((route) => [route.mode, route])
) as Record<Mode, RouteRegistryEntry>;

export const pageManifestBySegment = new Map(
  ROUTE_REGISTRY.filter((route) => route.routeSegment !== null).map(
    (route) => [route.routeSegment, route] as const
  )
);

export const MENU_CATEGORY_ORDER: Record<MenuSection, readonly MenuCategory[]> =
  {
    user: ['dashboard', 'insights', 'goals', 'preferences'],
    support: ['operations', 'preferences'],
  };

export const menuCategories = {
  user: MENU_CATEGORY_ORDER.user.map((category) => ({
    id: category,
    titleKey: category,
  })),
  support: MENU_CATEGORY_ORDER.support.map((category) => ({
    id: category,
    titleKey: category,
  })),
} as const;

export function getPageManifestEntry(
  mode: Mode
): RouteRegistryEntry | undefined {
  return pageManifestByMode[mode];
}

export function deriveRouteFromPathname(pathname: string): DerivedRoute {
  const segments = pathname.split('/').filter(Boolean);
  const [first, slug = ''] = segments;

  if (!first) {
    return { mode: 'group', routeSegment: null, slug: '' };
  }

  if (first === 'input') {
    return { mode: 'transactions', routeSegment: 'transactions', slug };
  }

  const matchedRoute = pageManifestBySegment.get(first);
  if (!matchedRoute) {
    return { mode: 'movers', routeSegment: null, slug: slug || first };
  }

  return {
    mode: matchedRoute.mode,
    routeSegment: matchedRoute.routeSegment,
    slug,
  };
}

export function deriveModeFromPathname(pathname: string): Mode {
  return deriveRouteFromPathname(pathname).mode;
}

export function deriveBootstrapMode(
  pathname: string,
  state: 'loading' | 'config-error' | 'auth'
): Mode | 'loading' {
  return state === 'loading' ? 'loading' : deriveModeFromPathname(pathname);
}

export function buildPathForMode(
  mode: Mode,
  context: RoutePathContext = {}
): string {
  return pageManifestByMode[mode].defaultPath(context);
}

export function pathForMode(
  mode: Mode,
  context: RoutePathContext = {}
): string {
  return buildPathForMode(mode, context);
}

export function isModeEnabled(
  mode: Mode,
  tabs: TabsConfig,
  disabledTabs?: readonly string[]
): boolean {
  return tabs[mode] !== false && !disabledTabs?.includes(mode);
}

export function getMenuEntries(
  section: MenuSection
): Array<RouteRegistryEntry & { menuCategory: MenuCategory }> {
  return ROUTE_REGISTRY.filter(
    (entry) => entry.section === section && Boolean(entry.menuCategory)
  ).sort(
    (left, right) => (left.priority ?? 0) - (right.priority ?? 0)
  ) as Array<RouteRegistryEntry & { menuCategory: MenuCategory }>;
}

export function validatePageManifest() {
  const duplicateModes = new Set<string>();
  const duplicateSegments = new Set<string>();
  const seenModes = new Set<string>();
  const seenSegments = new Set<string>();

  for (const entry of ROUTE_REGISTRY) {
    if (seenModes.has(entry.mode)) duplicateModes.add(entry.mode);
    seenModes.add(entry.mode);

    if (entry.routeSegment) {
      if (seenSegments.has(entry.routeSegment))
        duplicateSegments.add(entry.routeSegment);
      seenSegments.add(entry.routeSegment);
    }
  }

  return {
    duplicateModes: [...duplicateModes],
    duplicateSegments: [...duplicateSegments],
  };
}

export const standalonePageRoutes = ROUTE_REGISTRY.filter((entry) =>
  Boolean(entry.routePath && entry.lazyComponent)
) as Array<
  RouteRegistryEntry & {
    routePath: string;
    lazyComponent: LazyExoticComponent<ComponentType>;
  }
>;
