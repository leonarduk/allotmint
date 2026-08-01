import { expect, test, type Page } from '@playwright/test';
import {
  applyAuth as applyAuthToken,
  DEFAULT_CONFIG_BODY,
  DEFAULT_GROUPS_BODY,
  DEFAULT_OWNERS_BODY,
  getActiveRouteMarker,
} from './support/smokeFixtures';

// Regression coverage for #5735 / PR #5741: an unlayered `button` reset in
// index.css previously outranked Tailwind's utilities layer, so the active
// nav category button rendered dark text on a near-black background in both
// themes. These tests assert the actual computed styles (not just class
// names) so a future change to the cascade layer or Menu.tsx that
// reintroduces the regression fails loudly here rather than only being
// caught by eyeballing a screenshot.

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken =
  process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;
const marketPath = new URL('/market', baseUrl).toString();

const applyAuth = (page: Page) => applyAuthToken(page, authToken);

// getComputedStyle can return colors in whatever notation the CSS declared
// them in (Tailwind v4 emits oklch()), so normalise via a 1x1 canvas — the
// canvas 2D context always reports back-converted sRGB regardless of the
// input color space/function.
const toRgbString = (page: Page, color: string): Promise<string> =>
  page.evaluate((value) => {
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
    return `rgb(${r}, ${g}, ${b})`;
  }, color);

// Reads the computed background/text/border colors that Tailwind's
// `bg-gray-100 text-gray-900 border-blue-600` utility classes resolve to in
// the current theme, via a throwaway off-screen element — avoids hard-coding
// palette values that would drift if Tailwind's color space/version changes.
const referenceActiveClassColors = (page: Page) =>
  page.evaluate(() => {
    const el = document.createElement('div');
    el.className = 'bg-gray-100 text-gray-900 border-blue-600 border-b-2';
    el.style.position = 'absolute';
    el.style.visibility = 'hidden';
    document.body.appendChild(el);
    const computed = getComputedStyle(el);
    const result = {
      backgroundColor: computed.backgroundColor,
      color: computed.color,
      borderBottomColor: computed.borderBottomColor,
    };
    el.remove();
    return result;
  });

const mockIdentityCatalogue = async (page: Page, theme: 'light' | 'dark') => {
  await page.route('**/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...DEFAULT_CONFIG_BODY, theme }),
    });
  });
  await page.route('**/owners', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DEFAULT_OWNERS_BODY),
    });
  });
  await page.route('**/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DEFAULT_GROUPS_BODY),
    });
  });
};

// Relative luminance / contrast ratio per the WCAG 2.x formula, computed
// from `rgb(r, g, b)` strings as returned by getComputedStyle.
const relativeLuminance = (rgb: string): number => {
  const [r, g, b] = rgb
    .match(/[\d.]+/g)!
    .slice(0, 3)
    .map(Number)
    .map((channel) => {
      const c = channel / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

const contrastRatio = (foreground: string, background: string): number => {
  const l1 = relativeLuminance(foreground);
  const l2 = relativeLuminance(background);
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
};

test.describe('nav active state contrast (#5754)', () => {
  for (const theme of ['light', 'dark'] as const) {
    test(`the active dashboard nav trigger is styled and legible in the ${theme} theme`, async ({
      page,
    }) => {
      await applyAuth(page);
      await mockIdentityCatalogue(page, theme);

      await page.goto(marketPath);

      const marker = getActiveRouteMarker(page);
      await expect(marker).toHaveAttribute('data-mode', 'market');

      // "market" belongs to the "dashboard" menu category, so its trigger
      // button is active (containsActiveTab) without opening the dropdown.
      const trigger = page.locator('#menu-trigger-dashboard');
      await expect(trigger).toBeVisible();

      const rawStyles = await trigger.evaluate((el) => {
        const computed = getComputedStyle(el);
        return {
          backgroundColor: computed.backgroundColor,
          color: computed.color,
          borderBottomColor: computed.borderBottomColor,
          borderBottomWidth: computed.borderBottomWidth,
        };
      });

      const [backgroundColor, color, borderBottomColor] = await Promise.all([
        toRgbString(page, rawStyles.backgroundColor),
        toRgbString(page, rawStyles.color),
        toRgbString(page, rawStyles.borderBottomColor),
      ]);

      const expected = await referenceActiveClassColors(page);
      const [expectedBg, expectedColor, expectedBorder] = await Promise.all([
        toRgbString(page, expected.backgroundColor),
        toRgbString(page, expected.color),
        toRgbString(page, expected.borderBottomColor),
      ]);

      expect(backgroundColor).toBe(expectedBg);
      expect(color).toBe(expectedColor);
      expect(borderBottomColor).toBe(expectedBorder);
      expect(rawStyles.borderBottomWidth).toBe('2px');

      // WCAG AA for normal-weight text requires a contrast ratio >= 4.5:1.
      const ratio = contrastRatio(color, backgroundColor);
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });
  }
});
