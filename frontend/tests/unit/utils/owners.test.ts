import { describe, expect, it } from 'vitest';
import {
  findOwnerForUser,
  pickDefaultOwner,
  sanitizeOwners,
} from '@/utils/owners';

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

describe('findOwnerForUser', () => {
  const owners = [
    { owner: 'alice', accounts: [] as string[], email: 'alice@example.com' },
    { owner: 'bob', accounts: [] as string[], email: 'bob@example.com' },
  ];

  it('returns the owner whose email matches the logged-in user', () => {
    expect(findOwnerForUser(owners, { email: 'bob@example.com' })?.owner).toBe('bob');
  });

  it('matches case-insensitively and ignores surrounding whitespace', () => {
    expect(findOwnerForUser(owners, { email: '  ALICE@EXAMPLE.COM  ' })?.owner).toBe(
      'alice',
    );
  });

  it('returns undefined when there is no logged-in user', () => {
    expect(findOwnerForUser(owners, null)).toBeUndefined();
    expect(findOwnerForUser(owners, undefined)).toBeUndefined();
  });

  it('returns undefined when no owner matches the user email', () => {
    expect(findOwnerForUser(owners, { email: 'nobody@example.com' })).toBeUndefined();
  });

  it('returns undefined when owners have no email set', () => {
    const noEmailOwners = [{ owner: 'demo', accounts: [] as string[] }];
    expect(findOwnerForUser(noEmailOwners, { email: 'demo@example.com' })).toBeUndefined();
  });
});

describe('pickDefaultOwner (#10753)', () => {
  const owners = [
    { owner: 'alex', email: 'alex@example.com', accounts: [] as string[] },
    { owner: 'steve', email: 'steve@example.com', accounts: [] as string[] },
  ];
  const steve = { email: 'steve@example.com' };

  it("defaults to the signed-in user's owner, not owners[0]", () => {
    expect(pickDefaultOwner(owners, steve)).toBe('steve');
  });

  it('lets a valid preferred (route) owner win over the user match', () => {
    expect(pickDefaultOwner(owners, steve, 'alex')).toBe('alex');
  });

  it('ignores a preferred owner that is not in the list', () => {
    expect(pickDefaultOwner(owners, steve, 'nobody')).toBe('steve');
  });

  it('falls back to owners[0] when no user matches', () => {
    expect(pickDefaultOwner(owners, null)).toBe('alex');
    expect(pickDefaultOwner(owners, { email: 'x@example.com' })).toBe('alex');
  });

  it('returns an empty string when there are no owners', () => {
    expect(pickDefaultOwner([], steve)).toBe('');
  });
});
