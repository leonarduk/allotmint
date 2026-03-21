import { describe, expect, it } from 'vitest';
import { MODES } from '@/modes';
import {
  deriveModeFromPathname,
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
    expect(pageManifest.map((page) => page.mode).sort()).toEqual(
      [...MODES].sort()
    );
  });

  it('keeps route segments unique and mode derivation aligned', () => {
    const seenSegments = new Set<string>();

    for (const page of pageManifest) {
      if (page.routeSegment === null) {
        expect(deriveModeFromPathname('/')).toBe(page.mode);
        continue;
      }

      expect(seenSegments.has(page.routeSegment)).toBe(false);
      seenSegments.add(page.routeSegment);
      expect(deriveModeFromPathname(`/${page.routeSegment}`)).toBe(page.mode);
    }
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
