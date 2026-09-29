import { describe, expect, it } from 'vitest';
import type { TabsConfig } from '@/ConfigContext';
import { buildChatPages } from '@/utils/chatPages';

const label = (mode: string) => `label:${mode}`;

describe('buildChatPages', () => {
  it('offers only enabled menu pages', () => {
    const tabs = { market: true, movers: false } as unknown as TabsConfig;
    const paths = buildChatPages(tabs, [], label).map((page) => page.path);
    expect(paths).toContain('/market');
    expect(paths).not.toContain('/movers');
  });

  it('respects disabledTabs', () => {
    const tabs = { market: true } as unknown as TabsConfig;
    expect(buildChatPages(tabs, ['market'], label)).toEqual([]);
  });

  it('opens the transactions list itself and offers /input separately', () => {
    const tabs = { transactions: true } as unknown as TabsConfig;
    expect(buildChatPages(tabs, [], label)).toEqual([
      { path: '/transactions', label: 'label:transactions' },
      { path: '/input', label: 'Account + holdings input' },
    ]);
  });
});
