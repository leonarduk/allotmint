import { setAuthToken } from './api';

// sessionStorage (not localStorage) so a demo session is scoped to this tab
// and is gone as soon as the tab closes — mirroring SESSION_KEY in
// awsUiAuth.ts. Never persist a demo session beyond that.
const DEMO_SESSION_KEY = 'demoSession';
const DEMO_ROUTE_PATH = '/demo';

/**
 * Detects a `/demo?token=<...>` visit (issue #7410), applies the token as
 * the API bearer token (mirroring applyCognitoIdToken() in main.tsx), marks
 * this tab as a read-only demo session, and rewrites the URL to the plain
 * app root so the token never lingers in the address bar, the tab title, or
 * a screenshot — there is no bespoke `/demo` page to land on.
 *
 * Returns true when a demo token was found and applied; the caller must
 * then skip the normal Cognito/Google bootstrap entirely (a demo token
 * fully replaces that flow for this tab). Returns false — with no side
 * effects — for any other route, or a `/demo` visit with no token, so that
 * case falls through to the normal sign-in flow untouched.
 */
export const applyDemoTokenFromUrl = (): boolean => {
  if (window.location.pathname !== DEMO_ROUTE_PATH) return false;

  const params = new URLSearchParams(window.location.search);
  const token = params.get('token')?.trim();
  if (!token) return false;

  setAuthToken(token);
  window.sessionStorage.setItem(DEMO_SESSION_KEY, 'true');
  window.history.replaceState({}, document.title, '/');
  return true;
};

/** True when the current tab is running a demo-token (read-only) session. */
export const isDemoSession = (): boolean =>
  window.sessionStorage.getItem(DEMO_SESSION_KEY) === 'true';

/**
 * Clears the demo session marker — on logout, or when a 401 shows the demo
 * token has expired. A demo session is never refreshed; expiry is the
 * intended end of it, so this simply lets the app fall back to the normal
 * sign-in wall.
 */
export const clearDemoSession = (): void => {
  window.sessionStorage.removeItem(DEMO_SESSION_KEY);
};
