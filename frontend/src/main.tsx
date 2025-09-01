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
import './i18n'
import { ConfigProvider } from './ConfigContext'
import { PriceRefreshProvider } from './PriceRefreshContext'
import InstrumentResearch from './pages/InstrumentResearch'
import { getConfig } from './api'
import LoginPage from './LoginPage'

function Root() {
  const [ready, setReady] = useState(false)
  const [needsAuth, setNeedsAuth] = useState(false)
  const [clientId, setClientId] = useState('')
  const [authed, setAuthed] = useState(false)

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
        <Route path="/*" element={<App />} />
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
        <BrowserRouter>
          <Routes>
            <Route path="/support" element={<Support />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/virtual" element={<VirtualPortfolio />} />
            <Route path="/compliance" element={<ComplianceWarnings />} />
            <Route path="/compliance/:owner" element={<ComplianceWarnings />} />
            <Route path="/research/:ticker" element={<InstrumentResearch />} />
            {/* Catch-all for app routes; keep last to avoid intercepting above paths */}
            <Route path="/*" element={<App />} />
          </Routes>
        </BrowserRouter>
      </PriceRefreshProvider>
    </ConfigProvider>
  </StrictMode>,
)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js');
  });
}
