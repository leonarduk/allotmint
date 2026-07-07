import type { Page } from '@playwright/test';
import type { z } from 'zod';
import {
  configContractSchema,
  groupsContractSchema,
  ownersContractSchema,
} from '../../src/contracts/apiContracts';

export type MockConfigBody = z.infer<typeof configContractSchema> & {
  // enable_family_mvp is not part of the versioned /config contract yet, but the
  // frontend already reads it (Family MVP route gating). configContractSchema is
  // .passthrough(), so carrying it here does not fail validation.
  enable_family_mvp?: boolean;
};
export type MockOwnersBody = z.infer<typeof ownersContractSchema>;
export type MockGroupsBody = z.infer<typeof groupsContractSchema>;

/**
 * Default mock response bodies for the identity-catalogue endpoints
 * (/config, /owners, /groups) that the app shell needs before it renders any
 * page component. Typed against the real zod contracts in
 * src/contracts/apiContracts.ts so a schema drift between these mocks and the
 * actual backend contract fails a test instead of passing silently — see
 * tests/unit/smokeFixtures.test.ts.
 */
export const DEFAULT_CONFIG_BODY: MockConfigBody = {
  app_env: 'test',
  theme: null,
  tabs: { trail: true, taxtools: true, 'trade-compliance': true, reports: true },
  relative_view_enabled: false,
  google_auth_enabled: false,
  google_client_id: null,
  disable_auth: true,
  allowed_emails: null,
  local_login_email: null,
  disabled_tabs: [],
  enable_family_mvp: false,
};

export const DEFAULT_OWNERS_BODY: MockOwnersBody = [
  {
    owner: 'demo-owner',
    full_name: 'Demo Owner',
    accounts: ['ISA'],
    has_transactions_artifact: false,
  },
];

export const DEFAULT_GROUPS_BODY: MockGroupsBody = [
  { slug: 'all', name: 'All portfolios', members: ['demo-owner'] },
];

/**
 * Set up core API mocks so the app does not show BackendUnavailableCard
 * when there is no backend (e.g. CI preview build). These provide the
 * minimum identity catalogue (/config, /owners, /groups) that the app
 * shell needs before it renders any page component.
 *
 * Tests that need to mock additional endpoints should call setupCoreMocks
 * first and then add their own route() calls. Tests that intentionally
 * override all three endpoints with their own handlers can skip this.
 */
export const setupCoreMocks = async (page: Page) => {
  await page.route('**/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DEFAULT_CONFIG_BODY),
    });
  });
  await page.route('**/owners', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DEFAULT_OWNERS_BODY),
    });
  });
  await page.route('**/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DEFAULT_GROUPS_BODY),
    });
  });
};

/**
 * Seed a valid auth token (localStorage + a not-yet-expired Cognito/AWS UI
 * session in sessionStorage) before navigation, so ensureAwsUiAuth() finds an
 * unexpired session and skips the hosted-UI redirect, which would otherwise
 * navigate away from the app before it renders. See awsUiAuth.ts
 * hasValidSession(). No-op when no auth token is configured for the run.
 */
export const applyAuth = async (page: Page, authToken: string | null) => {
  if (!authToken) {
    return;
  }

  await page.addInitScript((token: string) => {
    window.localStorage.setItem('authToken', token);
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: token, expiresAt: Date.now() + 60 * 60 * 1000 })
    );
  }, authToken);
};

export const getActiveRouteMarker = (page: Page) =>
  page.locator('[data-route-marker="active"], [data-testid="active-route-marker"]');

export const getBootstrapMarker = (page: Page) =>
  page.locator('[data-route-marker="bootstrap"], [data-testid="route-bootstrap-marker"]');
