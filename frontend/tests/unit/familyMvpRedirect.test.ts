import { describe, expect, it } from 'vitest';
import { getFamilyMvpRedirectPath } from '@/App';

describe('getFamilyMvpRedirectPath', () => {
  it('redirects non-MVP routes to the configured entry path', () => {
    expect(getFamilyMvpRedirectPath('/market', '')).toBe('/portfolio');
    expect(getFamilyMvpRedirectPath('/support', '')).toBe('/portfolio');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/transactions', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '?range=1y')).toBeNull();
  });

  it('redirects bare root to default portfolio entry path', () => {
    expect(getFamilyMvpRedirectPath('/', '')).toBe('/portfolio');
  });

  it('redirects group query routes to portfolio because group is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids')).toBe('/portfolio');
  });

  it('supports overriding the entry path when a different MVP route is enabled', () => {
    expect(getFamilyMvpRedirectPath('/', '', '/performance')).toBe('/performance');
    expect(getFamilyMvpRedirectPath('/support', '', '/transactions')).toBe('/transactions');
  });
});
