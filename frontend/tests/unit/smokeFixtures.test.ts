import { describe, expect, it } from 'vitest';
import {
  configContractSchema,
  groupsContractSchema,
  ownersContractSchema,
} from '@/contracts/apiContracts';
import {
  DEFAULT_CONFIG_BODY,
  DEFAULT_GROUPS_BODY,
  DEFAULT_OWNERS_BODY,
} from '../support/smokeFixtures';

// Playwright smoke tests mock /config, /owners, /groups by hand (see
// smokeFixtures.ts) instead of hitting a real backend. If those mock bodies
// drift from the backend contract, smoke tests can pass while exercising a
// shape the real API would never send. Validating them against the same zod
// schemas used to check live API responses (src/contracts/apiContracts.ts)
// catches that drift at test time.
describe('smoke test mock fixtures', () => {
  it('DEFAULT_CONFIG_BODY satisfies the /config contract', () => {
    expect(() => configContractSchema.parse(DEFAULT_CONFIG_BODY)).not.toThrow();
  });

  it('DEFAULT_OWNERS_BODY satisfies the /owners contract', () => {
    expect(() => ownersContractSchema.parse(DEFAULT_OWNERS_BODY)).not.toThrow();
  });

  it('DEFAULT_GROUPS_BODY satisfies the /groups contract', () => {
    expect(() => groupsContractSchema.parse(DEFAULT_GROUPS_BODY)).not.toThrow();
  });
});
