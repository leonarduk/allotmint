import { describe, expect, it } from 'vitest';
import { getFamilyMvpRedirectPath } from '@/App';
import type { TabsConfig } from '@/ConfigContext';
import { getFamilyMvpEntryPath } from '@/familyMvp';

const baseTabs: TabsConfig = {
  group: true,
  market: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: false,
  screener: true,
  trading: true,
  timeseries: true,
  watchlist: true,
  allocation: true,
  rebalance: true,
  movers: true,
  instrumentadmin: true,
  dataadmin: true,
  virtual: true,
  research: true,
  support: true,
  settings: true,
  profile: false,
  alerts: true,
  pension: true,
  trail: false,
  alertsettings: true,
  taxtools: false,
  'trade-compliance': false,
  reports: false,
  scenario: true,
};

describe('getFamilyMvpRedirectPath', () => {
  it('does not redirect when family MVP is disabled', () => {
    expect(getFamilyMvpRedirectPath('/market', '', false)).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '', false)).toBeNull();
  });

  it('redirects non-MVP routes to transactions', () => {
    // entryPath defaults to /portfolio but at runtime familyMvpEntryPath
    // resolves to /transactions (first enabled FAMILY_MVP_ENTRY_CANDIDATE).
    // These tests pass the default explicitly to confirm function behaviour.
    expect(getFamilyMvpRedirectPath('/market', '', true)).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/support', '', true)).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/performance/alex', '', true)).toBe('/transactions');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/transactions', '', true)).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '', true)).toBeNull();
  });

  it('redirects bare root to the configured entry path', () => {
    expect(getFamilyMvpRedirectPath('/', '', true)).toBe('/transactions');
  });

  it('redirects group query routes to the entry path because group mode is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids', true)).toBe('/transactions');
  });

  it('redirects non-MVP routes to an explicit entry path override', () => {
    expect(getFamilyMvpRedirectPath('/market', '', true, '/portfolio')).toBe('/portfolio');
    expect(getFamilyMvpRedirectPath('/support', '', true, '/portfolio')).toBe('/portfolio');
  });

  it('does not redirect MVP routes regardless of entry path', () => {
    expect(getFamilyMvpRedirectPath('/portfolio', '', true, '/portfolio')).toBeNull();
    expect(getFamilyMvpRedirectPath('/transactions', '', true)).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '', true)).toBeNull();
  });

  it('supports overriding the entry path when a different MVP route is enabled', () => {
    expect(getFamilyMvpRedirectPath('/', '', true, '/performance')).toBe('/performance');
    expect(getFamilyMvpRedirectPath('/support', '', true, '/transactions')).toBe('/transactions');
  it('redirects non-MVP routes to the configured entry path', () => {
    expect(getFamilyMvpRedirectPath('/market', '')).toBe('/input');
    expect(getFamilyMvpRedirectPath('/support', '')).toBe('/input');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/portfolio', '', '/portfolio')).toBeNull();
    expect(getFamilyMvpRedirectPath('/input', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/transactions', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '')).toBeNull();
    expect(
      getFamilyMvpRedirectPath('/performance/alex', '?range=1y')
    ).toBeNull();
  });

  it('redirects bare root to default portfolio entry path', () => {
    expect(getFamilyMvpRedirectPath('/', '')).toBe('/input');
  });

  it('redirects group query routes because group mode is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids')).toBe('/input');
  });

  it('supports overriding the entry path when a different MVP route is enabled', () => {
    expect(getFamilyMvpRedirectPath('/', '', '/performance')).toBe(
      '/performance'
    );
    expect(getFamilyMvpRedirectPath('/support', '', '/input')).toBe('/input');
  });

  it('skips redirecting when every family MVP route is disabled (null entryPath)', () => {
    expect(getFamilyMvpRedirectPath('/', '', true, null)).toBeNull();
    expect(getFamilyMvpRedirectPath('/support', '', true, null)).toBeNull();
  });
});

describe('getFamilyMvpEntryPath', () => {
  it('prefers input, then portfolio, then performance', () => {
    expect(getFamilyMvpEntryPath({ ...baseTabs, transactions: true })).toBe(
      '/input'
    );
    expect(getFamilyMvpEntryPath(baseTabs)).toBe('/portfolio');
    expect(getFamilyMvpEntryPath({ ...baseTabs, owner: false })).toBe(
      '/performance'
    );
    expect(
      getFamilyMvpEntryPath({
        ...baseTabs,
        owner: false,
        performance: false,
        transactions: true,
      })
    ).toBe('/input');
  });

  it('respects disabledTabs over enabled tab values', () => {
    expect(
      getFamilyMvpEntryPath(
        {
          ...baseTabs,
          owner: true,
          performance: true,
        },
        ['owner']
      )
    ).toBe('/performance');
  });

  it('returns null when every family MVP route is disabled', () => {
    expect(
      getFamilyMvpEntryPath(
        {
          ...baseTabs,
          owner: false,
          performance: false,
          transactions: false,
        },
        ['owner', 'performance', 'transactions']
      )
    ).toBeNull();
  });
});
