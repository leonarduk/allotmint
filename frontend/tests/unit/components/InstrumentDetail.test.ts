import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  canExpandDrawer,
  clampDrawerWidth,
  expandedDrawerWidth,
} from '@/components/instrumentDetailDrawer';
import { readDrawerWidth } from '@/components/useInstrumentDetailDrawer';

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

describe('drawer expansion', () => {
  it('only offers expansion when it can make the default drawer wider', () => {
    expect(canExpandDrawer(600)).toBe(false);
    expect(canExpandDrawer(1200)).toBe(true);
    expect(expandedDrawerWidth(1200)).toBe(720);
  });
});

describe('readDrawerWidth', () => {
  afterEach(() => vi.restoreAllMocks());

  it('falls back to the default width when local storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled');
    });
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    expect(readDrawerWidth()).toBe(420);
    expect(console.warn).toHaveBeenCalledOnce();
  });
});
