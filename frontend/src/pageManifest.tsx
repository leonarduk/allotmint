import { lazy } from "react";
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
  routePatterns: readonly string[];
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
    routePatterns: ["/"],
    order: 0,
    menu: { section: "user", category: "dashboard" },
    path: ({ group }) =>
      group && !isDefaultGroupSlug(group) ? `/?group=${group}` : "/",
  },
  {
    mode: "market",
    routeSegment: "market",
    routePatterns: ["/market"],
    order: 5,
    menu: { section: "user", category: "dashboard" },
    path: () => "/market",
  },
  {
    mode: "movers",
    routeSegment: "movers",
    routePatterns: ["/movers"],
    order: 10,
    menu: { section: "user", category: "dashboard" },
    path: () => "/movers",
  },
  {
    mode: "instrument",
    routeSegment: "instrument",
    routePatterns: ["/instrument", "/instrument/:group"],
    order: 20,
    menu: { section: "user", category: "insights" },
    path: ({ group }) => (group ? `/instrument/${group}` : "/instrument"),
  },
  {
    mode: "owner",
    routeSegment: "portfolio",
    routePatterns: ["/portfolio", "/portfolio/:owner"],
    order: 30,
    menu: { section: "user", category: "dashboard" },
    path: ({ owner }) => (owner ? `/portfolio/${owner}` : "/portfolio"),
  },
  {
    mode: "performance",
    routeSegment: "performance",
    routePatterns: ["/performance", "/performance/:owner"],
    order: 40,
    menu: { section: "user", category: "dashboard" },
    path: ({ owner }) => (owner ? `/performance/${owner}` : "/performance"),
  },
  {
    mode: "transactions",
    routeSegment: "transactions",
    routePatterns: ["/transactions"],
    order: 50,
    menu: { section: "user", category: "dashboard" },
    path: () => "/transactions",
  },
  {
    mode: "trading",
    routeSegment: "trading",
    routePatterns: ["/trading"],
    order: 55,
    menu: { section: "user", category: "insights" },
    path: () => "/trading",
  },
  {
    mode: "screener",
    routeSegment: "screener",
    routePatterns: ["/screener"],
    order: 60,
    menu: { section: "user", category: "insights" },
    path: () => "/screener",
  },
  {
    mode: "timeseries",
    routeSegment: "timeseries",
    routePatterns: ["/timeseries"],
    order: 70,
    menu: { section: "support", category: "operations" },
    path: () => "/timeseries",
  },
  {
    mode: "watchlist",
    routeSegment: "watchlist",
    routePatterns: ["/watchlist"],
    order: 80,
    menu: { section: "user", category: "insights" },
    path: () => "/watchlist",
  },
  {
    mode: "allocation",
    routeSegment: "allocation",
    routePatterns: ["/allocation"],
    order: 85,
    menu: { section: "user", category: "dashboard" },
    path: () => "/allocation",
  },
  {
    mode: "instrumentadmin",
    routeSegment: "instrumentadmin",
    routePatterns: ["/instrumentadmin"],
    order: 85,
    menu: { section: "support", category: "operations" },
    path: () => "/instrumentadmin",
  },
  {
    mode: "rebalance",
    routeSegment: "rebalance",
    routePatterns: ["/rebalance"],
    order: 86,
    menu: { section: "user", category: "insights" },
    path: () => "/rebalance",
  },
  {
    mode: "dataadmin",
    routeSegment: "dataadmin",
    routePatterns: ["/dataadmin"],
    order: 90,
    menu: { section: "support", category: "operations" },
    path: () => "/dataadmin",
  },
  {
    mode: "reports",
    routeSegment: "reports",
    routePatterns: ["/reports", "/reports/new", "/reports/new/:templateId"],
    order: 100,
    menu: { section: "user", category: "dashboard" },
    path: () => "/reports",
  },
  {
    mode: "trail",
    routeSegment: "trail",
    routePatterns: ["/trail"],
    order: 102,
    menu: { section: "user", category: "goals" },
    path: () => "/trail",
  },
  {
    mode: "alertsettings",
    routeSegment: "alert-settings",
    routePatterns: ["/alert-settings"],
    order: 104,
    menu: { section: "user", category: "preferences" },
    path: () => "/alert-settings",
  },
  {
    mode: "settings",
    routeSegment: "settings",
    routePatterns: ["/settings"],
    order: 105,
    menu: { section: "user", category: "preferences" },
    path: () => "/settings",
  },
  {
    mode: "pension",
    routeSegment: "pension",
    routePatterns: ["/pension", "/pension/forecast"],
    order: 107,
    menu: { section: "user", category: "goals" },
    path: () => "/pension/forecast",
  },
  {
    mode: "taxtools",
    routeSegment: "tax-tools",
    routePatterns: ["/tax-tools"],
    order: 108,
    menu: { section: "user", category: "goals" },
    path: () => "/tax-tools",
  },
  {
    mode: "trade-compliance",
    routeSegment: "trade-compliance",
    routePatterns: ["/trade-compliance", "/trade-compliance/:owner"],
    order: 110,
    menu: { section: "user", category: "goals" },
    path: () => "/trade-compliance",
  },
  {
    mode: "support",
    routeSegment: "support",
    routePatterns: ["/support"],
    order: 110,
    menu: { section: "support", category: "preferences" },
    path: () => "/support",
  },
  {
    mode: "scenario",
    routeSegment: "scenario",
    routePatterns: ["/scenario"],
    order: 120,
    menu: { section: "user", category: "insights" },
    path: () => "/scenario",
  },
  {
    mode: "virtual",
    routeSegment: "virtual",
    routePatterns: ["/virtual"],
    order: 130,
    path: () => "/virtual",
  },
  {
    mode: "research",
    routeSegment: "research",
    routePatterns: ["/research", "/research/:ticker"],
    order: 140,
    path: () => "/research",
  },
] as const;

export interface StandalonePageRoute {
  path: string;
  mode: Mode | "loading";
  component: ReturnType<typeof lazy>;
}

export const STANDALONE_PAGE_ROUTES: readonly StandalonePageRoute[] = [
  {
    path: "/support",
    mode: "support",
    component: lazy(() => import("./pages/Support")),
  },
  {
    path: "/virtual",
    mode: "virtual",
    component: lazy(() => import("./pages/VirtualPortfolio")),
  },
  {
    path: "/trade-compliance",
    mode: "trade-compliance",
    component: lazy(() => import("./pages/TradeCompliance")),
  },
  {
    path: "/trade-compliance/:owner",
    mode: "trade-compliance",
    component: lazy(() => import("./pages/TradeCompliance")),
  },
  {
    path: "/alert-settings",
    mode: "alertsettings",
    component: lazy(() => import("./pages/AlertSettings")),
  },
  {
    path: "/trail",
    mode: "trail",
    component: lazy(() => import("./pages/Trail")),
  },
  {
    path: "/compliance",
    mode: "loading",
    component: lazy(() => import("./pages/ComplianceWarnings")),
  },
  {
    path: "/compliance/:owner",
    mode: "loading",
    component: lazy(() => import("./pages/ComplianceWarnings")),
  },
  {
    path: "/alerts",
    mode: "loading",
    component: lazy(() => import("./pages/Alerts")),
  },
  {
    path: "/goals",
    mode: "loading",
    component: lazy(() => import("./pages/Goals")),
  },
  {
    path: "/smoke-test",
    mode: "loading",
    component: lazy(() => import("./pages/SmokeTest")),
  },
  {
    path: "/performance/:owner/diagnostics",
    mode: "loading",
    component: lazy(() => import("./pages/PerformanceDiagnostics")),
  },
  {
    path: "/returns/compare",
    mode: "loading",
    component: lazy(() => import("./pages/ReturnComparison")),
  },
  {
    path: "/metrics-explained",
    mode: "loading",
    component: lazy(() => import("./pages/MetricsExplanation")),
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
  const duplicateRoutes = new Set<string>();
  const seenModes = new Set<string>();
  const seenSegments = new Set<string>();
  const seenRoutes = new Set<string>();

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

    for (const routePattern of entry.routePatterns) {
      if (seenRoutes.has(routePattern)) {
        duplicateRoutes.add(routePattern);
      }
      seenRoutes.add(routePattern);
    }
  }

  return {
    duplicateModes: Array.from(duplicateModes).sort(),
    duplicateSegments: Array.from(duplicateSegments).sort(),
    duplicateRoutes: Array.from(duplicateRoutes).sort(),
  };
}
