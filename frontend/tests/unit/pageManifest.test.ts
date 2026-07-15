import { describe, expect, it } from 'vitest';
import { MODES } from '@/modes';
import {
  buildPathForMode,
  deriveBootstrapMode,
  deriveModeFromPathname,
  deriveRouteFromPathname,
  menuCategories,
  pageManifest,
  pageManifestByMode,
  pathForMode,
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
    expect(buildPathForMode('owner', { owner: 'alex' })).toBe('/portfolio/alex');
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

      if (page.routeSegment !== null && page.mode !== 'group') {
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
});
