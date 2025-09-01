import { StrictMode } from 'react'
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

createRoot(document.getElementById('root')!).render(
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
