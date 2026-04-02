import { describe, expect, it } from 'vitest';
import { getFamilyMvpRedirectPath } from '@/App';

describe('getFamilyMvpRedirectPath', () => {
  it('redirects non-MVP routes to transactions', () => {
    expect(getFamilyMvpRedirectPath('/market', '')).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/support', '')).toBe('/transactions');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/transactions', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '')).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '?range=1y')).toBeNull();
  });

  it('redirects bare root to transactions for faster input flow', () => {
    expect(getFamilyMvpRedirectPath('/', '')).toBe('/transactions');
  });

  it('redirects group query routes to transactions because group is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids')).toBe('/transactions');
  });
});
