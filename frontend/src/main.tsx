import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './styles/responsive.css'
import './i18n'
import App from './App.tsx'
import VirtualPortfolio from './pages/VirtualPortfolio'
import Reports from './pages/Reports'
import Support from './pages/Support'
import ComplianceWarnings from './pages/ComplianceWarnings'
import { ConfigProvider } from './ConfigContext'
import { PriceRefreshProvider } from './PriceRefreshContext'
import InstrumentResearch from './pages/InstrumentResearch'
import { getConfig, setAuthToken } from './api'
import LoginPage from './LoginPage'

export function Root() {
  const [ready, setReady] = useState(false)
  const [needsAuth, setNeedsAuth] = useState(false)
  const [clientId, setClientId] = useState('')
  const [authed, setAuthed] = useState(false)

  const logout = () => {
    setAuthToken(null)
    setAuthed(false)
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
    <BrowserRouter>
      <Routes>
        <Route path="/support" element={<Support />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/virtual" element={<VirtualPortfolio />} />
        <Route path="/compliance" element={<ComplianceWarnings />} />
        <Route path="/compliance/:owner" element={<ComplianceWarnings />} />
        <Route path="/research/:ticker" element={<InstrumentResearch />} />
        <Route path="/*" element={<App onLogout={logout} />} />
      </Routes>
    </BrowserRouter>
  )
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');
createRoot(rootEl).render(
  <StrictMode>
    <ConfigProvider>
      <PriceRefreshProvider>
        <Root />
      </PriceRefreshProvider>
    </ConfigProvider>
  </StrictMode>,
)

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js');
  });
}
