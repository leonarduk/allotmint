import {
  StrictMode,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { createRoot } from 'react-dom/client';
import { HelmetProvider } from 'react-helmet-async';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import './index.css';
import './styles/responsive.css';
import './i18n';
import { ConfigProvider, useConfig } from './ConfigContext';
import { PriceRefreshProvider } from './PriceRefreshContext';
import { AuthProvider, useAuth } from './AuthContext';
import {
  getConfig,
  logout as apiLogout,
  getStoredAuthToken,
  setApiBase,
  setAuthToken,
} from './api';
import LoginPage from './LoginPage';
import { UserProvider, useUser } from './UserContext';
import ErrorBoundary from './ErrorBoundary';
import { loadStoredAuthUser, loadStoredUserProfile } from './authStorage';
import { RouteProvider } from './RouteContext';
import { clearCognitoSession, cognitoLogout, ensureAwsUiAuth, extractTokenExchangeErrorReason, getCognitoSessionExpiresAt, getStoredCognitoIdToken, refreshCognitoSession, UserCancelledError, type AwsUiAuthConfig } from './awsUiAuth';
import {
  deriveBootstrapMode,
  deriveModeFromPathname,
  isModeEnabled,
  standalonePageRoutes,
} from './pageManifest';

interface BootstrapConfig {
  google_auth_enabled?: boolean | null;
  google_client_id?: string | null;
  disable_auth?: boolean;
  local_login_email?: string | null;
  allowed_emails?: string[] | null;
}

const storedToken = getStoredAuthToken();
if (storedToken) setAuthToken(storedToken);

// Populated by bootstrapRuntimeConfig before React mounts so Root can pass it
// to LoginPage for the explicit Cognito sign-in button.
let runtimeAwsUiAuth: AwsUiAuthConfig | undefined;

const App = lazy(() => import('./App.tsx'));
const ComplianceWarnings = lazy(() => import('./pages/ComplianceWarnings'));
const Goals = lazy(() => import('./pages/Goals'));
const PerformanceDiagnostics = lazy(
  () => import('./pages/PerformanceDiagnostics')
);
const ReturnComparison = lazy(() => import('./pages/ReturnComparison'));
const MetricsExplanation = lazy(() => import('./pages/MetricsExplanation'));
const SmokeTest = lazy(() => import('./pages/SmokeTest'));
const FAMILY_MVP_ROUTE_GATES: ReadonlyArray<{
  mode: Parameters<typeof isModeEnabled>[0];
  path: string;
}> = [
  { mode: 'transactions', path: '/input' },
  { mode: 'transactions', path: '/transactions' },
  { mode: 'reports', path: '/reports' },
  { mode: 'taxtools', path: '/tax-tools' },
  { mode: 'trail', path: '/trail' },
  { mode: 'trade-compliance', path: '/trade-compliance' },
];

const routeMarkerStyle: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  border: 0,
  opacity: 0,
  pointerEvents: 'none',
  clip: 'rect(0 0 0 0)',
  clipPath: 'inset(50%)',
  overflow: 'hidden',
};

const renderRouteMarker = (
  pathname: string,
  state: 'loading' | 'config-error' | 'auth'
) => {
  const mode = deriveModeFromPathname(pathname);
  const bootstrapMode = deriveBootstrapMode(pathname, state);

  return (
    <>
      <div
        data-route-marker="bootstrap"
        data-testid="route-bootstrap-marker"
        data-mode={bootstrapMode}
        data-pathname={pathname}
        data-route-state={state}
        style={routeMarkerStyle}
      />
      <div
        data-route-marker="active"
        data-testid="active-route-marker"
        data-mode={mode}
        data-pathname={pathname}
        data-route-state={state}
        style={routeMarkerStyle}
      />
    </>
  );
};

export function Root({ awsUiAuth = runtimeAwsUiAuth }: { awsUiAuth?: AwsUiAuthConfig } = {}) {
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<Error | null>(null);
  const [retryScheduled, setRetryScheduled] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [googleLoginEnabled, setGoogleLoginEnabled] = useState(false);
  const [clientId, setClientId] = useState('');
  const [authed, setAuthed] = useState(
    Boolean(storedToken) || Boolean(getStoredCognitoIdToken()),
  );
  const { setUser } = useAuth();
  const { setProfile } = useUser();
  const navigate = useNavigate();
  const location = useLocation();
  const { tabs, disabledTabs } = useConfig();
  const complianceRoutesEnabled = isModeEnabled(
    'trade-compliance',
    tabs,
    disabledTabs
  );
  const advancedAnalyticsEnabled = isModeEnabled(
    'scenario',
    tabs,
    disabledTabs
  );
  const activeRequest = useRef<AbortController | null>(null);
  const retryTimer = useRef<number | null>(null);
  const isMounted = useRef(true);

  const clearRetryTimer = useCallback(() => {
    if (retryTimer.current !== null) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  }, []);

  const logout = () => {
    clearCognitoRefreshTimer();
    apiLogout();
    setUser(null);
    setProfile(undefined);
    setAuthed(false);
    if (awsUiAuth?.enabled) {
      cognitoLogout(awsUiAuth);
    } else {
      navigate('/');
    }
  };

  useEffect(() => {
    if (!storedToken) return;
    const existingUser = loadStoredAuthUser();
    if (existingUser) setUser(existingUser);
    const existingProfile = loadStoredUserProfile();
    if (existingProfile) setProfile(existingProfile);
  }, [setProfile, setUser]);

  const fetchConfig = useCallback(
    (attempt = 0, { manual = false }: { manual?: boolean } = {}) => {
      if (!isMounted.current) return;

      clearRetryTimer();

      const previousController = activeRequest.current;
      const controller = new AbortController();
      activeRequest.current = controller;
      if (previousController && previousController !== controller) {
        previousController.abort();
      }

      const timeoutMs = Math.min(60000, 30000 + attempt * 10000);
      const timeoutId = window.setTimeout(() => {
        controller.abort();
      }, timeoutMs);

      setConfigLoading(true);
      if (manual) {
        setConfigError(null);
        setRetryScheduled(false);
      }

      let shouldRetry = false;
      let retryDelay = 0;
      let nextAttempt = attempt;

      getConfig<BootstrapConfig>({ signal: controller.signal })
        .then((cfg) => {
          if (!isMounted.current || activeRequest.current !== controller)
            return;

          const configAuthEnabled = cfg.google_auth_enabled === true;
          const disableAuth = cfg.disable_auth === true;
          const configuredClientId =
            typeof cfg.google_client_id === 'string'
              ? cfg.google_client_id
              : '';
          const localLoginEmail =
            typeof cfg.local_login_email === 'string'
              ? cfg.local_login_email.trim()
              : '';
          // Backend auth semantics: null/empty allowed_emails means no allowlist
          // enforcement (allow all users). Keep this normalization explicit to
          // avoid accidental "deny all" behavior in future bootstrap guards.
          const allowedEmails = Array.isArray(cfg.allowed_emails)
            ? cfg.allowed_emails
            : [];
          void allowedEmails;

          setGoogleLoginEnabled(configAuthEnabled);
          setClientId(configuredClientId);
          // Backend semantics:
          // - disable_auth controls whether login is required.
          // - allowed_emails may be null (no explicit allowlist) without
          //   changing whether auth is required.
          // awsUiAuth.enabled means API Gateway enforces Cognito JWT auth
          // independently of disable_auth (which only tells the Lambda to skip
          // its own auth check — API Gateway still validates the Cognito JWT
          // before the Lambda is ever invoked). Treat awsUiAuth as requiring
          // auth so users without a session see the login page rather than
          // hitting 401 on protected endpoints like /groups.
          const awsUiAuthEnabled =
            awsUiAuth?.enabled === true || awsUiAuth?.enabled === 'true';
          setNeedsAuth(!disableAuth || awsUiAuthEnabled);

          if (disableAuth && localLoginEmail) {
            const storedUser = loadStoredAuthUser();
            if (!storedUser || storedUser.email !== localLoginEmail) {
              setUser({ email: localLoginEmail });
            }
            const storedProfile = loadStoredUserProfile();
            if (!storedProfile || storedProfile.email !== localLoginEmail) {
              setProfile({ email: localLoginEmail });
            }
          }

          setConfigError(null);
          setRetryScheduled(false);
        })
        .catch((err) => {
          if (!isMounted.current || activeRequest.current !== controller)
            return;

          console.error('Failed to load configuration', err);
          const error =
            err instanceof DOMException && err.name === 'AbortError'
              ? new Error('Request timed out while loading configuration.')
              : err instanceof Error
                ? err
                : new Error(String(err));
          setConfigError(error);
          shouldRetry = true;
          nextAttempt = attempt + 1;
          retryDelay = Math.min(30000, 2000 * 2 ** attempt);
        })
        .finally(() => {
          window.clearTimeout(timeoutId);
          const isCurrent =
            isMounted.current && activeRequest.current === controller;
          if (isCurrent) {
            activeRequest.current = null;
            setConfigLoading(false);
            if (shouldRetry) setRetryScheduled(true);
          }
          if (shouldRetry && isMounted.current) {
            retryTimer.current = window.setTimeout(() => {
              fetchConfig(nextAttempt);
            }, retryDelay);
          }
        });
    },
    [awsUiAuth, clearRetryTimer, setProfile, setUser]
  );

  useEffect(() => {
    isMounted.current = true;
    fetchConfig();
    return () => {
      isMounted.current = false;
      clearRetryTimer();
      activeRequest.current?.abort();
    };
  }, [clearRetryTimer, fetchConfig]);

  const handleRetry = useCallback(() => {
    fetchConfig(0, { manual: true });
  }, [fetchConfig]);

  const isPublicSupportRoute = location.pathname === '/support';
  const isPublicCreateAccountRoute = location.pathname === '/create-account';

  if (configLoading || retryScheduled) {
    return (
      <>
        {renderRouteMarker(location.pathname, 'loading')}
        <div role="status" className="app-loading">
          {retryScheduled ? 'Loading... retrying configuration.' : 'Loading configuration...'}
        </div>
      </>
    );
  }

  if (configError) {
    return (
      <>
        {renderRouteMarker(location.pathname, 'config-error')}
        <div role="alert" className="app-offline">
          <p>Unable to load configuration.</p>
          <p>Please check your connection and try again.</p>
          <button type="button" onClick={handleRetry}>
            Retry
          </button>
        </div>
      </>
    );
  }

  if (needsAuth && !authed && !isPublicSupportRoute && !isPublicCreateAccountRoute) {
    const awsUiAuthEnabled =
      awsUiAuth?.enabled === true || awsUiAuth?.enabled === 'true';
    const hasAnyLoginMethod =
      (googleLoginEnabled && Boolean(clientId)) || awsUiAuthEnabled;

    if (!hasAnyLoginMethod) {
      console.error(
        'Authentication is enforced but no login method is configured'
      );
      return (
        <>
          {renderRouteMarker(location.pathname, 'auth')}
          <div>Google login is not configured.</div>
        </>
      );
    }

    return (
      <>
        {renderRouteMarker(location.pathname, 'auth')}
        <LoginPage
          clientId={clientId}
          awsUiAuth={awsUiAuth}
          onSuccess={() => setAuthed(true)}
        />
      </>
    );
  }

  return (
    <ErrorBoundary key={location.pathname}>
      <Suspense fallback={<div>Loading...</div>}>
        <Routes>
          {complianceRoutesEnabled ? (
            <>
              <Route path="/compliance" element={<ComplianceWarnings />} />
              <Route
                path="/compliance/:owner"
                element={<ComplianceWarnings />}
              />
            </>
          ) : null}
          {standalonePageRoutes.flatMap((route) => {
            if (route.routePath === '/virtual' || !route.lazyComponent) {
              return [];
            }
            if (!isModeEnabled(route.mode, tabs, disabledTabs)) {
              return [];
            }

            const Component = route.lazyComponent;
            return [
              <Route
                key={route.routePath}
                path={route.routePath}
                element={<Component />}
              />,
            ];
          })}
          {FAMILY_MVP_ROUTE_GATES.flatMap(({ mode, path }) =>
            isModeEnabled(mode, tabs, disabledTabs)
              ? []
              : [
                  <Route
                    key={`disabled-${path}`}
                    path={path}
                    element={<Navigate to="/" replace />}
                  />,
                ]
          )}
          <Route path="/goals" element={<Goals />} />
          <Route path="/smoke-test" element={<SmokeTest />} />
          {advancedAnalyticsEnabled ? (
            <>
              <Route
                path="/performance/:owner/diagnostics"
                element={<PerformanceDiagnostics />}
              />
              <Route path="/returns/compare" element={<ReturnComparison />} />
              <Route
                path="/metrics-explained"
                element={<MetricsExplanation />}
              />
            </>
          ) : null}
          <Route
            path="/*"
            element={
              <RouteProvider>
                <App onLogout={logout} />
              </RouteProvider>
            }
          />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');

const applyCognitoIdToken = (awsUiAuth?: AwsUiAuthConfig | null): boolean => {
  // API Gateway protects /owners and every other /{proxy+} route with a Cognito
  // JWT authorizer whose audience is the UI app client ID (see
  // cdk/stacks/backend_lambda_stack.py BackendCognitoAuthorizer). That authorizer
  // matches the token's `aud` claim, which Cognito sets on the ID token (not the
  // access token). So the ID token must be sent verbatim as the
  // `Authorization: Bearer` header — exchanging it for a backend HS256 JWT (the
  // old /token/cognito flow) produced a token the gateway authorizer cannot
  // validate, returning 401 before the Lambda ran. See issue #4256.
  //
  // ensureAwsUiAuth() also returns true on the Google/local path (Cognito
  // disabled), so both values are guarded: with no clientId (not the Cognito
  // path) or no stored ID token there is nothing to apply, and we must NOT
  // disturb a backend JWT that the Google flow may have stored.
  const idToken = getStoredCognitoIdToken();
  const clientId = awsUiAuth?.clientId?.trim();
  if (!idToken || !clientId) return false;
  setAuthToken(idToken);
  return true;
};

// Refresh the Cognito ID token this far ahead of expiry so the Authorization
// header never goes stale mid-session (Cognito ID tokens last ~1h).
const COGNITO_REFRESH_BUFFER_MS = 5 * 60 * 1000;

let cognitoRefreshTimerId: number | null = null;

// Cancels any pending Cognito refresh timer so a stale refresh callback can't
// fire after logout or page unload. Idempotent.
const clearCognitoRefreshTimer = () => {
  if (cognitoRefreshTimerId !== null) {
    window.clearTimeout(cognitoRefreshTimerId);
    cognitoRefreshTimerId = null;
  }
};

const scheduleCognitoRefresh = (awsUiAuth?: AwsUiAuthConfig | null) => {
  clearCognitoRefreshTimer();
  const expiresAt = getCognitoSessionExpiresAt();
  if (expiresAt === null) return;
  // Clamp to >= 0 so an already-near-expiry session refreshes immediately
  // rather than scheduling a timer in the past.
  const delay = Math.max(0, expiresAt - Date.now() - COGNITO_REFRESH_BUFFER_MS);
  cognitoRefreshTimerId = window.setTimeout(() => {
    cognitoRefreshTimerId = null;
    void refreshCognitoSession(awsUiAuth)
      .then((idToken) => {
        if (idToken) {
          // Apply the fresh token and re-arm the timer for the new expiry.
          setAuthToken(idToken);
          scheduleCognitoRefresh(awsUiAuth);
          return;
        }
        // No refresh token / refresh rejected: drop the session so the next
        // reload restarts the hosted-UI login instead of looping on a dead token.
        console.error('Cognito token refresh failed — clearing session');
        clearCognitoSession();
        apiLogout();
      })
      .catch((error) => {
        console.error('Cognito token refresh failed — clearing session:', error);
        clearCognitoSession();
        apiLogout();
      });
  }, delay);
};

window.addEventListener('beforeunload', clearCognitoRefreshTimer);

const bootstrapRuntimeConfig = async () => {
  let payload: { apiBaseUrl?: unknown; awsUiAuth?: AwsUiAuthConfig } | undefined;
  try {
    const response = await fetch('/config.json', { cache: 'no-store' });
    if (!response.ok) return true;
    payload = (await response.json()) as {
      apiBaseUrl?: unknown;
      awsUiAuth?: AwsUiAuthConfig;
    };
  } catch (error) {
    console.warn(
      'Runtime config not loaded, using default API base URL',
      error
    );
    return true;
  }

  if (!payload) return true;

  if (typeof payload.apiBaseUrl === 'string') {
    setApiBase(payload.apiBaseUrl);
  }
  runtimeAwsUiAuth = payload.awsUiAuth;
  const shouldRender = await ensureAwsUiAuth(payload.awsUiAuth);
  if (shouldRender) {
    try {
      if (applyCognitoIdToken(payload.awsUiAuth)) {
        // Keep the ID token fresh for the lifetime of this session.
        scheduleCognitoRefresh(payload.awsUiAuth);
      }
    } catch (error) {
      console.error('Cognito authentication failed — clearing session:', error);
      // Clear both the Cognito session (prevents infinite retry loop on next load)
      // and the stored auth token so the app renders the login page.
      clearCognitoSession();
      apiLogout();
    }
  }
  return shouldRender;
};

void bootstrapRuntimeConfig()
  .then((shouldRender) => {
    if (!shouldRender) return;
    createRoot(rootEl).render(
      <StrictMode>
        <HelmetProvider>
          <ConfigProvider>
            <PriceRefreshProvider>
              <AuthProvider>
                <UserProvider>
                  <BrowserRouter>
                    <Root />
                  </BrowserRouter>
                  <ToastContainer autoClose={5000} />
                </UserProvider>
              </AuthProvider>
            </PriceRefreshProvider>
          </ConfigProvider>
        </HelmetProvider>
      </StrictMode>
    );
  })
  .catch((error) => {
    console.error('AWS UI authentication bootstrap failed', error);
    if (error instanceof UserCancelledError) {
      createRoot(rootEl).render(
        <div role="alert" className="app-offline">
          <p>Login cancelled.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Sign in
          </button>
        </div>
      );
    } else {
      const reason = extractTokenExchangeErrorReason(error);
      createRoot(rootEl).render(
        <div role="alert" className="app-offline">
          <p>Authentication is unavailable. Please contact your administrator.</p>
          {reason && <p>Sign-in failed. Reason: {reason}</p>}
          <button type="button" onClick={() => window.location.reload()}>
            Sign in
          </button>
        </div>
      );
    }
  });
