import { describe, expect, it } from 'vitest';
import { sanitizeOwners } from '@/utils/owners';

const makeOwner = (owner: string) => ({ owner, accounts: [] as string[] });

describe('sanitizeOwners', () => {
  it('filters demo owner when real owners exist', () => {
    const owners = [makeOwner('demo'), makeOwner('alice'), makeOwner('bob')];
    expect(sanitizeOwners(owners)).toEqual([makeOwner('alice'), makeOwner('bob')]);
  });

  it('keeps demo owner when it is the only option', () => {
    const owners = [makeOwner('demo')];
    expect(sanitizeOwners(owners)).toEqual([makeOwner('demo')]);
  });

  it('returns empty list when no owners provided', () => {
    expect(sanitizeOwners([])).toEqual([]);
  });
});
