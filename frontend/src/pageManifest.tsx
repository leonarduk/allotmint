import type { TabsConfig } from "./ConfigContext";
import type { Mode } from "./modes";
import { isDefaultGroupSlug } from "./utils/groups";

export type MenuSection = "user" | "support";
export type MenuCategory =
  | "dashboard"
  | "insights"
  | "goals"
  | "preferences"
  | "operations";

export interface PagePathContext {
  owner?: string;
  group?: string;
}

export interface PageManifestEntry {
  mode: Mode;
  routeSegment?: string;
  order: number;
  menu?: {
    section: MenuSection;
    category: MenuCategory;
  };
  path: (context: PagePathContext) => string;
}

export const PAGE_MANIFEST: readonly PageManifestEntry[] = [
  {
    mode: "group",
    order: 0,
    menu: { section: "user", category: "dashboard" },
    path: ({ group }) =>
      group && !isDefaultGroupSlug(group) ? `/?group=${group}` : "/",
  },
  {
    mode: "market",
    routeSegment: "market",
    order: 5,
    menu: { section: "user", category: "dashboard" },
    path: () => "/market",
  },
  {
    mode: "movers",
    routeSegment: "movers",
    order: 10,
    menu: { section: "user", category: "dashboard" },
    path: () => "/movers",
  },
  {
    mode: "instrument",
    routeSegment: "instrument",
    order: 20,
    menu: { section: "user", category: "insights" },
    path: ({ group }) => (group ? `/instrument/${group}` : "/instrument"),
  },
  {
    mode: "owner",
    routeSegment: "portfolio",
    order: 30,
    menu: { section: "user", category: "dashboard" },
    path: ({ owner }) => (owner ? `/portfolio/${owner}` : "/portfolio"),
  },
  {
    mode: "performance",
    routeSegment: "performance",
    order: 40,
    menu: { section: "user", category: "dashboard" },
    path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
  },
  {
    mode: "transactions",
    routeSegment: "transactions",
    order: 50,
    menu: { section: "user", category: "dashboard" },
    path: () => "/transactions",
  },
  {
    mode: "trading",
    routeSegment: "trading",
    order: 55,
    menu: { section: "user", category: "insights" },
    path: () => "/trading",
  },
  {
    mode: "screener",
    routeSegment: "screener",
    order: 60,
    menu: { section: "user", category: "insights" },
    path: () => "/screener",
  },
  {
    mode: "timeseries",
    routeSegment: "timeseries",
    order: 70,
    menu: { section: "support", category: "operations" },
    path: () => "/timeseries",
  },
  {
    mode: "watchlist",
    routeSegment: "watchlist",
    order: 80,
    menu: { section: "user", category: "insights" },
    path: () => "/watchlist",
  },
  {
    mode: "allocation",
    routeSegment: "allocation",
    order: 85,
    menu: { section: "user", category: "dashboard" },
    path: () => "/allocation",
  },
  {
    mode: "instrumentadmin",
    routeSegment: "instrumentadmin",
    order: 85,
    menu: { section: "support", category: "operations" },
    path: () => "/instrumentadmin",
  },
  {
    mode: "rebalance",
    routeSegment: "rebalance",
    order: 86,
    menu: { section: "user", category: "insights" },
    path: () => "/rebalance",
  },
  {
    mode: "dataadmin",
    routeSegment: "dataadmin",
    order: 90,
    menu: { section: "support", category: "operations" },
    path: () => "/dataadmin",
  },
  {
    mode: "reports",
    routeSegment: "reports",
    order: 100,
    menu: { section: "user", category: "dashboard" },
    path: () => "/reports",
  },
  {
    mode: "trail",
    routeSegment: "trail",
    order: 102,
    menu: { section: "user", category: "goals" },
    path: () => "/trail",
  },
  {
    mode: "alertsettings",
    routeSegment: "alert-settings",
    order: 104,
    menu: { section: "user", category: "preferences" },
    path: () => "/alert-settings",
  },
  {
    mode: "settings",
    routeSegment: "settings",
    order: 105,
    menu: { section: "user", category: "preferences" },
    path: () => "/settings",
  },
  {
    mode: "pension",
    routeSegment: "pension",
    order: 107,
    menu: { section: "user", category: "goals" },
    path: () => "/pension/forecast",
  },
  {
    mode: "taxtools",
    routeSegment: "tax-tools",
    order: 108,
    menu: { section: "user", category: "goals" },
    path: () => "/tax-tools",
  },
  {
    mode: "trade-compliance",
    routeSegment: "trade-compliance",
    order: 110,
    menu: { section: "user", category: "goals" },
    path: () => "/trade-compliance",
  },
  {
    mode: "support",
    routeSegment: "support",
    order: 110,
    menu: { section: "support", category: "preferences" },
    path: () => "/support",
  },
  {
    mode: "scenario",
    routeSegment: "scenario",
    order: 120,
    menu: { section: "user", category: "insights" },
    path: () => "/scenario",
  },
  {
    mode: "virtual",
    routeSegment: "virtual",
    order: 130,
    path: () => "/virtual",
  },
  {
    mode: "research",
    routeSegment: "research",
    order: 140,
    path: () => "/research",
  },
] as const;

export const MENU_CATEGORY_ORDER: Record<MenuSection, readonly MenuCategory[]> = {
  user: ["dashboard", "insights", "goals", "preferences"],
  support: ["operations", "preferences"],
};

export function getPageManifestEntry(mode: Mode): PageManifestEntry | undefined {
  return PAGE_MANIFEST.find((entry) => entry.mode === mode);
}

export function deriveModeFromPathname(pathname: string): Mode {
  const segments = pathname.split("/").filter(Boolean);
  const [first] = segments;

  if (!first) {
    return "group";
  }

  const entry = PAGE_MANIFEST.find((candidate) => candidate.routeSegment === first);
  return entry?.mode ?? "movers";
}

export function buildPathForMode(mode: Mode, context: PagePathContext = {}): string {
  return getPageManifestEntry(mode)?.path(context) ?? `/${mode}`;
}

export function isModeEnabled(
  mode: Mode,
  tabs: TabsConfig,
  disabledTabs?: readonly string[],
): boolean {
  return tabs[mode] !== false && !disabledTabs?.includes(mode);
}

export function getMenuEntries(section: MenuSection): PageManifestEntry[] {
  return PAGE_MANIFEST.filter(
    (entry): entry is PageManifestEntry & { menu: NonNullable<PageManifestEntry["menu"]> } =>
      entry.menu?.section === section,
  ).sort((left, right) => left.order - right.order);
}

export function validatePageManifest() {
  const duplicateModes = new Set<string>();
  const duplicateSegments = new Set<string>();
  const seenModes = new Set<string>();
  const seenSegments = new Set<string>();

  for (const entry of PAGE_MANIFEST) {
    if (seenModes.has(entry.mode)) {
      duplicateModes.add(entry.mode);
    }
    seenModes.add(entry.mode);

    if (entry.routeSegment) {
      if (seenSegments.has(entry.routeSegment)) {
        duplicateSegments.add(entry.routeSegment);
      }
      seenSegments.add(entry.routeSegment);
    }
  }

  return {
    duplicateModes: Array.from(duplicateModes),
    duplicateSegments: Array.from(duplicateSegments),
  };
}
