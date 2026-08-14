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
});
