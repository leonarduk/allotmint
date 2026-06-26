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
  // #4641: Family MVP controls ONLY the default landing page. The bare root
  // ('/' with no query) redirects to the entry path; every other route — even
  // non-MVP routes like /market, /support, /research — is left untouched so
  // enabled tabs stay fully navigable.

  it('does not redirect when family MVP is disabled', () => {
    expect(getFamilyMvpRedirectPath('/market', '', false)).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '', false)).toBeNull();
    expect(getFamilyMvpRedirectPath('/', '', false, '/transactions')).toBeNull();
  });

  it('redirects bare root to the configured entry path', () => {
    expect(getFamilyMvpRedirectPath('/', '', true, '/transactions')).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/', '', true, '/portfolio')).toBe('/portfolio');
    expect(getFamilyMvpRedirectPath('/', '', true, '/performance')).toBe('/performance');
  });

  it('does NOT redirect non-MVP routes back to the entry path', () => {
    // Previously these bounced to the entry path; now they must stay put so the
    // search bar, settings link and other enabled tabs work in Family MVP mode.
    expect(getFamilyMvpRedirectPath('/market', '', true, '/transactions')).toBeNull();
    expect(getFamilyMvpRedirectPath('/support', '', true, '/transactions')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '', true, '/transactions')).toBeNull();
    expect(getFamilyMvpRedirectPath('/research/MSFT', '', true, '/transactions')).toBeNull();
    expect(getFamilyMvpRedirectPath('/settings', '', true, '/transactions')).toBeNull();
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/transactions', '', true)).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '', true)).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio', '', true, '/portfolio')).toBeNull();
  });

  it('does not redirect a group query route (it carries a query string)', () => {
    // '/' only redirects when there is no search; '/?group=kids' is left alone.
    expect(getFamilyMvpRedirectPath('/', '?group=kids', true, '/transactions')).toBeNull();
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
