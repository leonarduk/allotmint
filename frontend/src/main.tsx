import {
  StrictMode,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { createRoot } from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import { ToastContainer } from 'react-toastify'
import 'react-toastify/dist/ReactToastify.css'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import './index.css'
import './styles/responsive.css'
import './i18n'
import { ConfigProvider } from './ConfigContext'
import { PriceRefreshProvider } from './PriceRefreshContext'
import { AuthProvider, useAuth } from './AuthContext'
import { getConfig, logout as apiLogout, getStoredAuthToken, setAuthToken } from './api'
import LoginPage from './LoginPage'
import { UserProvider, useUser } from './UserContext'
import ErrorBoundary from './ErrorBoundary'
import { loadStoredAuthUser, loadStoredUserProfile } from './authStorage'
import { RouteProvider } from './RouteContext'

const storedToken = getStoredAuthToken()
if (storedToken) setAuthToken(storedToken)

const App = lazy(() => import('./App.tsx'))
const VirtualPortfolio = lazy(() => import('./pages/VirtualPortfolio'))
const Support = lazy(() => import('./pages/Support'))
const ComplianceWarnings = lazy(() => import('./pages/ComplianceWarnings'))
const TradeCompliance = lazy(() => import('./pages/TradeCompliance'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Goals = lazy(() => import('./pages/Goals'))
const Trail = lazy(() => import('./pages/Trail'))
const PerformanceDiagnostics = lazy(() => import('./pages/PerformanceDiagnostics'))
const ReturnComparison = lazy(() => import('./pages/ReturnComparison'))
const AlertSettings = lazy(() => import('./pages/AlertSettings'))
const MetricsExplanation = lazy(() => import('./pages/MetricsExplanation'))
const SmokeTest = lazy(() => import('./pages/SmokeTest'))

export function Root() {
  const [configLoading, setConfigLoading] = useState(true)
  const [configError, setConfigError] = useState<Error | null>(null)
  const [retryScheduled, setRetryScheduled] = useState(false)
  const [needsAuth, setNeedsAuth] = useState(false)
  const [clientId, setClientId] = useState('')
  const [authed, setAuthed] = useState(Boolean(storedToken))
  const { setUser } = useAuth()
  const { setProfile } = useUser()
  const navigate = useNavigate()
  const location = useLocation()
  const activeRequest = useRef<AbortController | null>(null)
  const retryTimer = useRef<number | null>(null)
  const isMounted = useRef(true)

  const clearRetryTimer = useCallback(() => {
    if (retryTimer.current !== null) {
      window.clearTimeout(retryTimer.current)
      retryTimer.current = null
    }
  }, [])

  const logout = () => {
    apiLogout()
    setUser(null)
    setProfile(undefined)
    setAuthed(false)
    navigate('/')
  }

  useEffect(() => {
    if (!storedToken) return
    const existingUser = loadStoredAuthUser()
    if (existingUser) setUser(existingUser)
    const existingProfile = loadStoredUserProfile()
    if (existingProfile) setProfile(existingProfile)
  }, [setProfile, setUser, storedToken])

  const fetchConfig = useCallback(
    (attempt = 0, { manual = false }: { manual?: boolean } = {}) => {
      if (!isMounted.current) return

      clearRetryTimer()

      const previousController = activeRequest.current
      const controller = new AbortController()
      activeRequest.current = controller
      if (previousController && previousController !== controller) {
        previousController.abort()
      }

      const timeoutMs = Math.min(60000, 30000 + attempt * 10000)
      const timeoutId = window.setTimeout(() => {
        controller.abort()
      }, timeoutMs)

      setConfigLoading(true)
      if (manual) {
        setConfigError(null)
        setRetryScheduled(false)
      }

      let shouldRetry = false
      let retryDelay = 0
      let nextAttempt = attempt

      getConfig<Record<string, unknown>>({ signal: controller.signal })
        .then(cfg => {
          if (!isMounted.current || activeRequest.current !== controller) return
          setNeedsAuth(Boolean((cfg as any).google_auth_enabled))
          setClientId(String((cfg as any).google_client_id || ''))
          setConfigError(null)
          setRetryScheduled(false)
        })
        .catch(err => {
          if (!isMounted.current || activeRequest.current !== controller) return
          console.error('Failed to load configuration', err)
          const error =
            err instanceof DOMException && err.name === 'AbortError'
              ? new Error('Request timed out while loading configuration.')
              : err instanceof Error
              ? err
              : new Error(String(err))
          setConfigError(error)

          shouldRetry = true
          nextAttempt = attempt + 1
          retryDelay = Math.min(30000, 2000 * 2 ** attempt)
        })
        .finally(() => {
          window.clearTimeout(timeoutId)
          const isCurrent = isMounted.current && activeRequest.current === controller
          if (isCurrent) {
            activeRequest.current = null
            setConfigLoading(false)
            if (shouldRetry) {
              setRetryScheduled(true)
            }
          }
          if (shouldRetry && isMounted.current) {
            retryTimer.current = window.setTimeout(() => {
              fetchConfig(nextAttempt)
            }, retryDelay)
          }
        })
    },
    [clearRetryTimer],
  )

  useEffect(() => {
    isMounted.current = true
    fetchConfig()
    return () => {
      isMounted.current = false
      clearRetryTimer()
      activeRequest.current?.abort()
    }
  }, [clearRetryTimer, fetchConfig])

  const handleRetry = useCallback(() => {
    fetchConfig(0, { manual: true })
  }, [fetchConfig])

  if (configLoading && !retryScheduled) {
    return (
      <div role="status" className="app-loading">
        Loading configuration...
      </div>
    )
  }

  if (configError && !retryScheduled) {
    return (
      <div role="alert" className="app-offline">
        <p>Unable to load configuration.</p>
        <p>Please check your connection and try again.</p>
        <button type="button" onClick={handleRetry}>
          Retry
        </button>
      </div>
    )
  }
  if (needsAuth && !authed) {
    if (!clientId) {
      console.error('Google client ID is missing; login disabled')
      return <div>Google login is not configured.</div>
    }
    return <LoginPage clientId={clientId} onSuccess={() => setAuthed(true)} />
  }

  return (
    <ErrorBoundary key={location.pathname}>
      <Suspense fallback={<div>Loading...</div>}>
        <Routes>
          <Route path="/support" element={<Support />} />
          <Route path="/virtual" element={<VirtualPortfolio />} />
          <Route path="/compliance" element={<ComplianceWarnings />} />
          <Route path="/compliance/:owner" element={<ComplianceWarnings />} />
          <Route path="/trade-compliance" element={<TradeCompliance />} />
          <Route path="/trade-compliance/:owner" element={<TradeCompliance />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/alert-settings" element={<AlertSettings />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/trail" element={<Trail />} />
          <Route path="/smoke-test" element={<SmokeTest />} />
          <Route path="/performance/:owner/diagnostics" element={<PerformanceDiagnostics />} />
          <Route path="/returns/compare" element={<ReturnComparison />} />
          <Route path="/metrics-explained" element={<MetricsExplanation />} />
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
  )
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');
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
  </StrictMode>,
)

if (
  'serviceWorker' in navigator &&
  (import.meta.env.PROD || import.meta.env.VITE_ENABLE_SW)
) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .catch(err => console.error('Service worker registration failed:', err))
  })
}
