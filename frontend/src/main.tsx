import { StrictMode, useEffect, useState, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import { ToastContainer } from 'react-toastify'
import 'react-toastify/dist/ReactToastify.css'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import './index.css'
import './styles/responsive.css'
import './i18n'
import { ConfigProvider } from './ConfigContext'
import { PriceRefreshProvider } from './PriceRefreshContext'
import { AuthProvider, useAuth } from './AuthContext'
import { getConfig, logout as apiLogout, getStoredAuthToken, setAuthToken } from './api'
import LoginPage from './LoginPage'
import { UserProvider } from './UserContext'
import { FocusModeProvider } from './FocusModeContext'

const storedToken = getStoredAuthToken()
if (storedToken) setAuthToken(storedToken)

const App = lazy(() => import('./App.tsx'))
const VirtualPortfolio = lazy(() => import('./pages/VirtualPortfolio'))
const Support = lazy(() => import('./pages/Support'))
const ComplianceWarnings = lazy(() => import('./pages/ComplianceWarnings'))
const TradeCompliance = lazy(() => import('./pages/TradeCompliance'))
const InstrumentResearch = lazy(() => import('./pages/InstrumentResearch'))
const Profile = lazy(() => import('./pages/Profile'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Goals = lazy(() => import('./pages/Goals'))
const PerformanceDiagnostics = lazy(() => import('./pages/PerformanceDiagnostics'))
const ReturnComparison = lazy(() => import('./pages/ReturnComparison'))
const AlertSettings = lazy(() => import('./pages/AlertSettings'))
const SmokeTest = import.meta.env.VITE_SMOKE_TEST
  ? lazy(() => import('./pages/SmokeTest'))
  : null

export function Root() {
  const [ready, setReady] = useState(false)
  const [needsAuth, setNeedsAuth] = useState(false)
  const [clientId, setClientId] = useState('')
  const [authed, setAuthed] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()

  const logout = () => {
    apiLogout()
    setUser(null)
    setAuthed(false)
    navigate('/')
  }

  useEffect(() => {
    getConfig<Record<string, unknown>>()
      .then(cfg => {
        setNeedsAuth(Boolean((cfg as any).google_auth_enabled))
        setClientId(String((cfg as any).google_client_id || ''))
      })
      .finally(() => setReady(true))
  }, [])

  if (!ready) return null
  if (needsAuth && !authed) {
    if (!clientId) {
      console.error('Google client ID is missing; login disabled')
      return <div>Google login is not configured.</div>
    }
    return <LoginPage clientId={clientId} onSuccess={() => setAuthed(true)} />
  }

  return (
    <Suspense fallback={<div>Loading...</div>}>
      <Routes>
        <Route path="/support" element={<Support />} />
        <Route path="/virtual" element={<VirtualPortfolio />} />
        <Route path="/compliance" element={<ComplianceWarnings />} />
        <Route path="/compliance/:owner" element={<ComplianceWarnings />} />
        <Route path="/trade-compliance" element={<TradeCompliance />} />
        <Route path="/trade-compliance/:owner" element={<TradeCompliance />} />
        <Route path="/research/:ticker" element={<InstrumentResearch />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/alert-settings" element={<AlertSettings />} />
        <Route path="/goals" element={<Goals />} />
        {import.meta.env.VITE_SMOKE_TEST && SmokeTest && (
          <Route path="/smoke-test" element={<SmokeTest />} />
        )}
        <Route path="/performance/:owner/diagnostics" element={<PerformanceDiagnostics />} />
        <Route path="/returns/compare" element={<ReturnComparison />} />
        <Route path="/*" element={<App onLogout={logout} />} />
      </Routes>
    </Suspense>
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
              <FocusModeProvider>
                <BrowserRouter>
                  <Root />
                </BrowserRouter>
                <ToastContainer autoClose={5000} />
              </FocusModeProvider>
            </UserProvider>
          </AuthProvider>
        </PriceRefreshProvider>
      </ConfigProvider>
    </HelmetProvider>
  </StrictMode>,
)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .catch(err => console.error('Service worker registration failed:', err))
  })
}
