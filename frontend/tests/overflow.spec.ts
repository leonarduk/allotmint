import { test, expect, Page } from '@playwright/test';

/**
 * Mobile horizontal-overflow regression tests.
 *
 * Context: PR #7240 fixed a mobile overflow bug by adding `min-width: 0`
 * to `.cropCardWrap` and `.cropCard` (plus a precautionary `min-width: 0`
 * on `.tray`) in `plot.module.css`. These tests lock in that fix by
 * asserting there is no horizontal scrollbar at common mobile widths on
 * the routes that render the affected components.
 *
 * If `min-width: 0` is removed from `.cropCardWrap` or `.cropCard`, the
 * assertions below should fail (scrollWidth > clientWidth).
 */

const ROUTES = ['/plot', '/plot/crops', '/plot/season'] as const;

const VIEWPORTS = [
  { name: '320x568', width: 320, height: 568 },
  { name: '375x667', width: 375, height: 667 },
  { name: '414x736', width: 414, height: 736 },
] as const;

/**
 * Wait for the page to be fully rendered before measuring layout.
 * We wait for network idle (data fetching settled) and for the root
 * element to be present, then give the browser a frame to flush layout.
 */
async function waitForStableLayout(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('body', { state: 'attached' });
  // Allow the browser to complete a layout/paint pass before measuring.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

async function getOverflowMetrics(page: Page): Promise<{
  scrollWidth: number;
  clientWidth: number;
}> {
  return page.evaluate(() => {
    const el = document.documentElement;
    return {
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    };
  });
}

test.describe('mobile horizontal overflow', () => {
  for (const route of ROUTES) {
    for (const viewport of VIEWPORTS) {
      test(`${route} has no horizontal overflow at ${viewport.name}`, async ({
        page,
      }) => {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });

        await page.goto(route);
        await waitForStableLayout(page);

        const { scrollWidth, clientWidth } = await getOverflowMetrics(page);

        expect(
          scrollWidth,
          `Expected no horizontal overflow on ${route} at ${viewport.name} ` +
            `(scrollWidth=${scrollWidth}, clientWidth=${clientWidth})`,
        ).toBe(clientWidth);
      });
    }
  }
});

test.describe('known-problematic elements stay within their container', () => {
  // These selectors correspond to the elements fixed in PR #7240.
  // They may not exist on every route, so we only assert when present.
  const SELECTORS = ['.cropCardWrap', '.cropCard', '.tray'];

  for (const route of ROUTES) {
    for (const viewport of VIEWPORTS) {
      test(`${route} at ${viewport.name}: cards/tray do not exceed parent width`, async ({
        page,
      }) => {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });

        await page.goto(route);
        await waitForStableLayout(page);

        for (const selector of SELECTORS) {
          const offenders = await page.evaluate((sel) => {
            const nodes = Array.from(document.querySelectorAll(sel));
            const results: Array<{
              selector: string;
              childWidth: number;
              parentWidth: number;
            }> = [];
            for (const node of nodes) {
              const parent = node.parentElement;
              if (!parent) continue;
              const childRect = node.getBoundingClientRect();
              const parentRect = parent.getBoundingClientRect();
              // Allow a 1px tolerance for sub-pixel rounding.
              if (childRect.width > parentRect.width + 1) {
                results.push({
                  selector: sel,
                  childWidth: childRect.width,
                  parentWidth: parentRect.width,
                });
              }
            }
            return results;
          }, selector);

          expect(
            offenders,
            `Element(s) ${selector} exceed parent width on ${route} at ${viewport.name}: ` +
              JSON.stringify(offenders),
          ).toEqual([]);
        }
      });
    }
  }
});
