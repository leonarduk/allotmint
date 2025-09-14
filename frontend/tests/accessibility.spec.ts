import { test, expect } from '@playwright/test';

test('tab order and focus visibility', async ({ page }) => {
  await page.setContent(`
    <style>
      .focus-ring:focus-visible { outline: 2px solid blue; }
    </style>
    <button id="chip" class="focus-ring">Chip</button>
    <button id="tile" class="focus-ring">Tile</button>
    <button id="refresh" class="focus-ring">Refresh</button>
  `);

  await page.keyboard.press('Tab');
  await expect(page.locator('#chip')).toBeFocused();
  let outline = await page.locator('#chip').evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe('none');

  await page.keyboard.press('Tab');
  await expect(page.locator('#tile')).toBeFocused();
  outline = await page.locator('#tile').evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe('none');

  await page.keyboard.press('Tab');
  await expect(page.locator('#refresh')).toBeFocused();
  outline = await page.locator('#refresh').evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe('none');
});
