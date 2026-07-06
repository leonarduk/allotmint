import { describe, expect, it } from 'vitest';
import { findOwnerForUser, sanitizeOwners } from '@/utils/owners';

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
