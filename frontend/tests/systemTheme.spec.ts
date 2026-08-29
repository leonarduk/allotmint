import { expect, test, type Page } from '@playwright/test';
import {
  DEFAULT_CONFIG_BODY,
  DEFAULT_GROUPS_BODY,
  DEFAULT_OWNERS_BODY,
} from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';

const mockAppShell = async (page: Page, theme: 'dark' | 'light' | 'system') => {
  for (const [path, body] of [
    ['config', { ...DEFAULT_CONFIG_BODY, theme }],
    ['owners', DEFAULT_OWNERS_BODY],
    ['groups', DEFAULT_GROUPS_BODY],
  ] as const) {
    await page.route(`**/${path}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    );
  }
};

const readRootTheme = (page: Page) =>
  page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    // Production builds minify CSS, which can shorten 6-digit hex colors
    // (#ffffff) to their 3-digit shorthand (#fff) inside custom-property
    // values; expand back to 6 digits so this assertion is stable across
    // dev and preview/production builds.
    const expandHex = (value: string) => {
      const match = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(value);
      return match ? `#${match[1]}${match[1]}${match[2]}${match[2]}${match[3]}${match[3]}` : value;
    };
    return {
      attribute: document.documentElement.getAttribute('data-theme'),
      backgroundColor: styles.backgroundColor,
      colorScheme: styles.colorScheme,
      drawerBackground: expandHex(styles.getPropertyValue('--drawer-bg').trim().toLowerCase()),
    };
  });

test.describe('application theme', () => {
  test('system follows a light browser preference', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await mockAppShell(page, 'system');
    await page.goto(baseUrl);

    await expect
      .poll(() => readRootTheme(page))
      .toEqual({
        attribute: null,
        backgroundColor: 'rgb(255, 255, 255)',
        colorScheme: 'light',
        drawerBackground: '#ffffff',
      });
  });

  for (const override of ['dark', 'light'] as const) {
    test(`${override} overrides the browser preference`, async ({ page }) => {
      await page.emulateMedia({
        colorScheme: override === 'dark' ? 'light' : 'dark',
      });
      await mockAppShell(page, override);
      await page.goto(baseUrl);

      const expected =
        override === 'dark' ? 'rgb(36, 36, 36)' : 'rgb(255, 255, 255)';
      await expect
        .poll(() => readRootTheme(page))
        .toMatchObject({
          attribute: override,
          backgroundColor: expected,
          colorScheme: override,
        });
    });
  }
});
