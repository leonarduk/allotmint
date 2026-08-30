import { describe, expect, it } from 'vitest';
import { MODES } from '@/modes';
import {
  buildPathForMode,
  deriveBootstrapMode,
  deriveModeFromPathname,
  deriveModeFromLocation,
  deriveRouteFromPathname,
  getMenuEntries,
  menuCategories,
  pageManifest,
  pageManifestByMode,
  pathForMode,
  readRouteScopeQuery,
  standalonePageRoutes,
  standaloneRouteNeedsChrome,
  validatePageManifest,
} from '@/pageManifest';

const menuCategoryIds = new Set([
  ...menuCategories.user.map((category) => category.id),
  ...menuCategories.support.map((category) => category.id),
]);

describe('page manifest', () => {
  it('defines one manifest entry for every mode with no duplicate modes or segments', () => {
    expect(pageManifest.map((page) => page.mode).sort()).toEqual([...MODES].sort());

    const validation = validatePageManifest();
    expect(validation.duplicateModes).toEqual([]);
    expect(validation.duplicateSegments).toEqual([]);
  });

  it('keeps route segments unique and derives an identical mode from the runtime (App.tsx), bootstrap (main.tsx), and route-detail helpers for every registered route', () => {
    const seenSegments = new Set<string>();

    for (const page of pageManifest) {
      if (page.routeSegment === null) {
        expect(deriveRouteFromPathname('/')).toEqual({
          mode: page.mode,
          routeSegment: null,
          slug: '',
        });
        continue;
      }

      expect(seenSegments.has(page.routeSegment)).toBe(false);
      seenSegments.add(page.routeSegment);

      const pathname = `/${page.routeSegment}/example-slug`;
      const derivedRoute = deriveRouteFromPathname(pathname);
      expect(derivedRoute.mode).toBe(page.mode);
      expect(derivedRoute.routeSegment).toBe(page.routeSegment);
      expect(deriveModeFromPathname(pathname)).toBe(page.mode);
      expect(deriveBootstrapMode(pathname, 'auth')).toBe(page.mode);
      expect(deriveBootstrapMode(pathname, 'config-error')).toBe(page.mode);
      expect(deriveBootstrapMode(pathname, 'loading')).toBe('loading');
    }

    // Unknown segments still fall through to a single shared default.
    expect(deriveModeFromPathname('/totally-unknown')).toBe('movers');
    expect(deriveRouteFromPathname('/totally-unknown').mode).toBe('movers');

    // The default group slug still gets an explicit `group` query param (not
    // a bare '/') so it never collides with the Family MVP entry-path
    // redirect, which treats '/' with no query as "go to the entry page" (#5075).
    expect(buildPathForMode('group', { group: 'all' })).toBe('/?group=all');
    expect(buildPathForMode('group', { group: 'kids' })).toBe('/?group=kids');
    expect(buildPathForMode('owner', { owner: 'alex' })).toBe('/?owner=alex');
    expect(buildPathForMode('owner', { owner: 'Alex Smith' })).toBe(
      '/?owner=Alex%20Smith'
    );
    expect(buildPathForMode('transactions')).toBe('/input');
    expect(buildPathForMode('pension')).toBe('/pension/forecast');
  });

  it('scopes the performance default path to owner, then group, then unscoped (#7228)', () => {
    // Owner scope wins whenever an owner is selected -- this preserves the
    // path-segment form (and with it /performance/:owner/diagnostics)
    // exactly as it worked before group scope existed.
    expect(buildPathForMode('performance', { owner: 'alice' })).toBe(
      '/performance/alice'
    );

    // No owner selected but a group is (e.g. navigating the Performance nav
    // link while viewing the merged household Dashboard, where
    // selectedOwner is '' and selectedGroup defaults to 'all'): this is a
    // DELIBERATE choice to land on the household's combined performance
    // rather than silently narrowing to "my own" performance, matching the
    // Dashboard's own group-first default (`/?group=all`). Before #7228 this
    // returned a bare '/performance', which the owner-root redirect then
    // forced onto the signed-in user's own performance -- so this is an
    // intentional behaviour change, not an oversight.
    expect(buildPathForMode('performance', { group: 'all' })).toBe(
      '/performance?group=all'
    );
    expect(buildPathForMode('performance', { group: 'adults' })).toBe(
      '/performance?group=adults'
    );

    // Both present: owner still wins (e.g. a stale selectedGroup left over
    // from browsing another group-scoped mode must not hijack an explicit
    // owner selection).
    expect(
      buildPathForMode('performance', { owner: 'alice', group: 'all' })
    ).toBe('/performance/alice');

    // Neither present: falls through to the bare route, which the
    // owner-root redirect (getOwnerRootRedirectPath) then resolves once
    // owners have loaded.
    expect(buildPathForMode('performance')).toBe('/performance');
  });

  it('keeps menu metadata and default paths consistent for navigable pages', () => {
    for (const page of pageManifest) {
      if (page.section === 'standalone' && !page.menuCategory) {
        continue;
      }

      if (page.menuCategory) {
        expect(menuCategoryIds.has(page.menuCategory)).toBe(true);
      }

      const defaultPath = pathForMode(page.mode, {
        selectedGroup: 'income',
        selectedOwner: 'alice',
      });
      expect(defaultPath.startsWith('/')).toBe(true);

      if (
        page.routeSegment !== null &&
        page.mode !== 'group' &&
        page.mode !== 'owner'
      ) {
        // 'transactions' mode has routeSegment 'transactions' but its canonical
        // URL is '/input' (the entry screen). The segment and defaultPath are
        // intentionally mismatched — exclude it from the containment check.
        if (page.mode !== 'transactions') {
          expect(defaultPath).toContain(page.routeSegment);
        }
      }
    }
  });

  it('keeps standalone lazy routes wired through the manifest', () => {
    expect(standalonePageRoutes.length).toBeGreaterThan(0);

    for (const route of standalonePageRoutes) {
      expect(route.routePath).toBeTruthy();
      expect(route.lazyComponent).toBeTruthy();
      expect(pageManifestByMode[route.mode]).toBe(route);
    }
  });

  it('reads bookmarkable owner and account scope from the root URL', () => {
    expect(readRouteScopeQuery('?group=all&owner=Steve%20Smith&account=isa')).toEqual({
      group: 'all',
      owner: 'Steve Smith',
      account: 'isa',
    });
    expect(deriveModeFromLocation('/', '?owner=Steve%20Smith')).toBe('group');
    expect(deriveModeFromLocation('/', '?account=isa')).toBe('group');
    expect(
      deriveModeFromLocation('/portfolio/steve', '?account=isa')
    ).toBe('owner');
    // A conflicting `?owner=` query must not override pathname-mode routing:
    // /portfolio/:owner stays in 'owner' mode regardless of the query string.
    expect(
      deriveModeFromLocation('/portfolio/steve', '?owner=other')
    ).toBe('owner');
  });

  it('keeps the owner registry entry while making root query scope canonical', () => {
    expect(pageManifestByMode.owner.routeSegment).toBe('portfolio');
    expect(buildPathForMode('owner', { owner: 'Steve Smith' })).toBe(
      '/?owner=Steve%20Smith'
    );

    expect(deriveModeFromLocation('/', '?owner=steve&account=isa')).toBe(
      'group'
    );
    expect(deriveModeFromLocation('/portfolio/steve', '?account=isa')).toBe(
      'owner'
    );
    expect(readRouteScopeQuery('?owner=steve&account=isa')).toEqual({
      group: null,
      owner: 'steve',
      account: 'isa',
    });
  });

  it('hides the owner mode from the nav menu while keeping it routable (#6716)', () => {
    // The merged dashboard already exposes the owner-scoped view (with
    // import/reconcile/export) via its owner tabs, so 'Portfolio' must not
    // appear as a duplicate menu entry...
    expect(getMenuEntries('user').some((entry) => entry.mode === 'owner')).toBe(
      false
    );
    // ...but the registry entry stays so deep links and redirects keep
    // working: /portfolio/:owner -> /?owner=X and buildPathForMode('owner').
    expect(pageManifestByMode.owner.routeSegment).toBe('portfolio');
    expect(buildPathForMode('owner', { owner: 'Steve Smith' })).toBe(
      '/?owner=Steve%20Smith'
    );
  });

  it('wraps standalone routes in AppHeader except a small excluded set (#6725, #7226)', () => {
    // Every standalone-routed page gets nav chrome when mounted directly...
    expect(standaloneRouteNeedsChrome('/data-quality')).toBe(true);
    expect(standaloneRouteNeedsChrome('/data-explorer')).toBe(true);
    expect(standaloneRouteNeedsChrome('/trail')).toBe(true);
    expect(standaloneRouteNeedsChrome('/trade-compliance')).toBe(true);
    expect(standaloneRouteNeedsChrome('/virtual')).toBe(true);
    expect(standaloneRouteNeedsChrome('/help')).toBe(true);
    // /support now gets the shared AppHeader too (#7226): it's reachable
    // pre-login, but that's no reason to strand whoever lands there without
    // navigation.
    expect(standaloneRouteNeedsChrome('/support')).toBe(true);
    // ...except /alert-settings (self-renders AppHeader with lastRefresh)
    // and /create-account, the public pre-login route that must stay
    // chrome-free.
    expect(standaloneRouteNeedsChrome('/alert-settings')).toBe(false);
    expect(standaloneRouteNeedsChrome('/create-account')).toBe(false);
    // A route with no path (never mounted standalone) is not chrome-bearing.
    expect(standaloneRouteNeedsChrome(undefined)).toBe(false);
  });

  it('keeps the operations console out of the end-user menu and gives Help its place instead (#7226)', () => {
    // Support is section: 'support' like its operations siblings and now
    // shares their 'operations' menuCategory, so getMenuEntries('user')
    // never returns it and it only ever shows up alongside Data Admin /
    // Data Quality / Timeseries in getMenuEntries('support').
    expect(pageManifestByMode.support.section).toBe('support');
    expect(pageManifestByMode.support.menuCategory).toBe('operations');
    expect(
      getMenuEntries('user').some((entry) => entry.mode === 'support')
    ).toBe(false);
    expect(
      getMenuEntries('support').some((entry) => entry.mode === 'support')
    ).toBe(true);
    // Deep link stays intact for whoever retains access.
    expect(buildPathForMode('support')).toBe('/support');

    // A real, end-user-facing Help entry takes its old spot in Settings.
    expect(pageManifestByMode.help.section).toBe('user');
    expect(pageManifestByMode.help.menuCategory).toBe('preferences');
    expect(
      getMenuEntries('user').some((entry) => entry.mode === 'help')
    ).toBe(true);
    expect(buildPathForMode('help')).toBe('/help');
  });
});
