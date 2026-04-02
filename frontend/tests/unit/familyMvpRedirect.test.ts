import { describe, expect, it } from 'vitest';
import { getFamilyMvpRedirectPath } from '@/App';

describe('getFamilyMvpRedirectPath', () => {
  it('does not redirect when family MVP is disabled', () => {
    expect(getFamilyMvpRedirectPath('/market', '', false)).toBeNull();
    expect(getFamilyMvpRedirectPath('/performance/alex', '', false)).toBeNull();
  });

  it('redirects non-MVP routes to transactions', () => {
    expect(getFamilyMvpRedirectPath('/market', '', true)).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/support', '', true)).toBe('/transactions');
    expect(getFamilyMvpRedirectPath('/performance/alex', '', true)).toBe('/transactions');
  });

  it('does not redirect MVP routes', () => {
    expect(getFamilyMvpRedirectPath('/transactions', '', true)).toBeNull();
    expect(getFamilyMvpRedirectPath('/portfolio/alex', '', true)).toBeNull();
  });

  it('redirects bare root to transactions for faster input flow', () => {
    expect(getFamilyMvpRedirectPath('/', '', true)).toBe('/transactions');
  });

  it('redirects group query routes to transactions because group is non-MVP', () => {
    expect(getFamilyMvpRedirectPath('/', '?group=kids', true)).toBe('/transactions');
  });
});
