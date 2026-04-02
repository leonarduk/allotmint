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
  it('redirects non-MVP routes to the configured entry path', () => {
    expect(getFamilyMvpRedirectPath('/market', '')).toBe('/portfolio');
    expect(getFamilyMvpRedirectPath('/support', '')).toBe('/portfolio');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/portfolio', '', '/portfolio')).toBeNull();
    expect(getFamilyMvpRedirectPath('/transactions', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '?range=1y')).toBeNull();
  });

  it('redirects bare root to default portfolio entry path', () => {
    expect(getFamilyMvpRedirectPath('/', '')).toBe('/portfolio');
  });

  it('redirects group query routes because group mode is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids')).toBe('/portfolio');
  });

  it('supports overriding the entry path when a different MVP route is enabled', () => {
    expect(getFamilyMvpRedirectPath('/', '', '/performance')).toBe('/performance');
    expect(getFamilyMvpRedirectPath('/support', '', '/transactions')).toBe('/transactions');
  });

  it('skips redirecting when every family MVP route is disabled', () => {
    expect(getFamilyMvpRedirectPath('/', '', null)).toBeNull();
    expect(getFamilyMvpRedirectPath('/support', '', null)).toBeNull();
  });
});

describe('getFamilyMvpEntryPath', () => {
  it('prefers portfolio, then performance, then transactions', () => {
    expect(getFamilyMvpEntryPath(baseTabs)).toBe('/portfolio');
    expect(getFamilyMvpEntryPath({ ...baseTabs, owner: false })).toBe('/performance');
    expect(
      getFamilyMvpEntryPath({
        ...baseTabs,
        owner: false,
        performance: false,
        transactions: true,
      })
    ).toBe('/transactions');
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

