import { describe, expect, it } from 'vitest';

import { clampDrawerWidth } from '@/components/instrumentDetailDrawer';

describe('clampDrawerWidth', () => {
  it('keeps a requested drawer width within desktop viewport bounds', () => {
    expect(clampDrawerWidth(700, 1200)).toBe(700);
    expect(clampDrawerWidth(200, 1200)).toBe(320);
    expect(clampDrawerWidth(1400, 1200)).toBe(1184);
  });

  it('allows the drawer to fit a viewport narrower than its desktop minimum', () => {
    expect(clampDrawerWidth(420, 300)).toBe(300);
  });
});
