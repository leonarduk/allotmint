import { describe, expect, it } from 'vitest';
import { MODES } from '@/modes';
import {
  deriveBootstrapMode,
  deriveModeFromPathname,
  deriveRouteFromPathname,
  menuCategories,
  pageManifest,
  pageManifestByMode,
  pathForMode,
  standalonePageRoutes,
} from '@/pageManifest';

const menuCategoryIds = new Set([
  ...menuCategories.user.map((category) => category.id),
  ...menuCategories.support.map((category) => category.id),
]);

describe('page manifest', () => {
  it('defines one manifest entry for every mode', () => {
    expect(pageManifest.map((page) => page.mode).sort()).toEqual([...MODES].sort());
  });

  it('keeps route segments unique and mode derivation aligned', () => {
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

    expect(deriveModeFromPathname('/totally-unknown')).toBe('movers');
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
        page.mode !== 'transactions'
      ) {
        expect(defaultPath).toContain(page.routeSegment);
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
