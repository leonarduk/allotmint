import { describe, expect, it } from 'vitest';
import { sanitizeOwners } from '@/utils/owners';

const makeOwner = (owner: string) => ({ owner, accounts: [] as string[] });

describe('sanitizeOwners', () => {
  it('filters placeholder owners', () => {
    const owners = [
      makeOwner('demo'),
      makeOwner('.idea'),
      makeOwner('alice'),
      makeOwner('bob'),
    ];
    expect(sanitizeOwners(owners)).toEqual([makeOwner('alice'), makeOwner('bob')]);
  });

  it('retains demo owner when it is the only available option', () => {
    const owners = [makeOwner('demo'), makeOwner('.idea')];
    expect(sanitizeOwners(owners)).toEqual([makeOwner('demo')]);
  });

  it('returns empty list when no owners provided', () => {
    expect(sanitizeOwners([])).toEqual([]);
  });
});
